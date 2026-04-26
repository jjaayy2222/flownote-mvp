# backend/services/topic_clustering_service.py

"""
[Step 2-2 - Phase 2] 사용자 관심 토픽 클러스터링 서비스
=========================================================

설계 원칙 (개인정보 보호 우선):
  - user_id는 절대 Redis 키, 로그에 평문으로 기록하지 않는다.
  - 로그에 user_id를 출력해야 하는 경우 반드시 mask_pii_id() 헬퍼를 사용한다.
  - hashed_user_id 기반으로 Redis 키를 구성한다.

Cold Start 정책:
  - 완료된 챗봇 메시지 쌍(Q/A) 또는 유효 RAG 검색 수행 기록이 누적
    COLD_START_THRESHOLD(기본값: 5)건 미만인 사용자는 콜드 스타트로 분류한다.
  - 콜드 스타트 사용자에게는 개인화 클러스터링 없이 전역 인덱스 100% 폴백을 적용한다.

Redis 스키마:
  - 메시지 쌍 카운터 키  : "cls:msg_pair_count:{hashed_user_id}"   (string/int)
  - RAG 검색 카운터 키   : "cls:rag_search_count:{hashed_user_id}" (string/int)
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import typing
from typing import Any, Callable, Dict, List, Optional, TypeVar
from functools import lru_cache

import numpy as np
import redis.exceptions
from redis.exceptions import RedisError  # 연결/타임아웃/명령 실패 포괄
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from backend.services.redis_pubsub import redis_client  # type: ignore[import]
from backend.utils import mask_pii_id  # type: ignore[import]
from backend.embedding import EmbeddingGenerator  # type: ignore[import]
from fastapi.concurrency import run_in_threadpool  # type: ignore[import]

logger = logging.getLogger(__name__)

# [Optimization] 임베딩 생성기 싱글톤 관리 (모듈 레벨)
_embedding_gen: Optional[EmbeddingGenerator] = None


def _get_embedding_generator() -> EmbeddingGenerator:
    """임베딩 생성기 인스턴스를 지연 로딩(Lazy Loading) 방식으로 반환한다."""
    global _embedding_gen
    if _embedding_gen is None:
        _embedding_gen = EmbeddingGenerator()
    return _embedding_gen


# [Preprocessing] 텍스트 정규화용 정규식
# [리뷰반영] Unicode-aware 패턴으로 변경: \w (문자·숫자·언더스코어) + \s 이외만 제거.
# 영문·한글뿐 아니라 일본어·아랍어 등 다국어 스크립트도 보존한다 (글로벌 사용자 대비).
# re.UNICODE는 Python 3의 기본값이므로 명시적 플래그 없이도 적용된다.
_CLEAN_RE = re.compile(r"[^\w\s]")  # 구두점·특수기호만 제거, 유니코드 문자 보존
_WS_RE = re.compile(r"\s+")  # 연속 공백 통합

# ─────────────────────────────────────────────────────────────────────────────
# 모듈 레벨 상수 (하드코딩 금지 — 모두 여기서 중앙 관리)
# ─────────────────────────────────────────────────────────────────────────────

# Redis 키 접두사
_MSG_PAIR_COUNT_PREFIX: str = "cls:msg_pair_count"
_RAG_SEARCH_COUNT_PREFIX: str = "cls:rag_search_count"
_QUERY_HISTORY_PREFIX: str = "cls:query_history"  # 사용자 검색어 히스토리 (List)
_CLUSTER_CACHE_PREFIX: str = "cls:result"         # 클러스터링 결과 캐시 (JSON String)

# 데이터 스키마 버전 (버전 업 시 구버전 캐시 자동 무효화, 환경 변수로 외부화)
_CLUSTER_CACHE_VERSION_ENV_KEY = "CLUSTER_CACHE_VERSION"
_CLUSTER_CACHE_VERSION_DEFAULT = "v1"

@lru_cache(maxsize=1)
def _get_cluster_cache_version() -> str:
    """
    [리뷰반영] CLUSTER_CACHE_VERSION 환경 변수를 지연 로드(lazy-load)하고 캐싱한다.
    lru_cache를 사용하여 스레드 안전성(Thread-Safety)을 보장하고 불필요한 전역 변수를 제거한다.
    """
    raw_val = os.environ.get(_CLUSTER_CACHE_VERSION_ENV_KEY)
    
    # 1) 미설정 시 조용히 기본값 사용하되, 최초 로딩 시점에 INFO 로그로 남겨 관측성 향상
    if raw_val is None:
        logger.info(
            "[TOPIC_CLUSTERING] %s 환경 변수가 미설정되었습니다. 기본값 %r을 사용합니다.",
            _CLUSTER_CACHE_VERSION_ENV_KEY,
            _CLUSTER_CACHE_VERSION_DEFAULT,
        )
        return _CLUSTER_CACHE_VERSION_DEFAULT

    val = raw_val.strip()
    # 2) 설정되었으나 공백인 경우 운영자 실수로 간주하여 WARNING 로그
    if not val:
        # 공백인 경우 원본 값(raw_val)을 repr()로 남겨 정확한 설정 문제 진단을 돕는다.
        logger.warning(
            "[TOPIC_CLUSTERING] %s 환경 변수가 비정상(공백)입니다 (운영자 오설정 의심, raw=%r). 기본값 %r로 폴백합니다.",
            _CLUSTER_CACHE_VERSION_ENV_KEY,
            raw_val,
            _CLUSTER_CACHE_VERSION_DEFAULT,
        )
        return _CLUSTER_CACHE_VERSION_DEFAULT

    return val

def clear_cluster_cache_version() -> None:
    """
    [리뷰반영] 핫 리로드(Hot Reload) 지원을 위한 명시적 캐시 초기화 함수.
    운영 환경에서 CLUSTER_CACHE_VERSION 환경 변수가 변경되었을 때 
    프로세스 재시작 없이 새 값을 반영하기 위해 사용할 수 있다.
    """
    _get_cluster_cache_version.cache_clear()

# 콜드 스타트 판별 임계값 (환경 변수로 외부화)
# COLD_START_THRESHOLD: 누적 활동 수가 이 값 미만이면 콜드 스타트로 간주
_COLD_START_THRESHOLD_ENV_KEY = "COLD_START_THRESHOLD"
_COLD_START_THRESHOLD_DEFAULT = 5
_COLD_START_THRESHOLD_MIN = 1
_COLD_START_THRESHOLD_MAX = 100

# 콜드 스타트 시 적용할 전역 인덱스 가중치 (환경 변수로 외부화)
# COLD_START_GLOBAL_INDEX_WEIGHT: 콜드 스타트 사용자에게 적용할 전역 인덱스 비율
_COLD_START_GLOBAL_WEIGHT_ENV_KEY = "COLD_START_GLOBAL_INDEX_WEIGHT"
_COLD_START_GLOBAL_WEIGHT_DEFAULT = 1.0
_COLD_START_GLOBAL_WEIGHT_MIN = 0.0
_COLD_START_GLOBAL_WEIGHT_MAX = 1.0


# 검색 히스토리 관리 설정
# SEARCH_HISTORY_MAX_LEN: 사용자별로 유지할 최근 검색어 최대 개수
_SEARCH_HISTORY_MAX_LEN_ENV_KEY = "SEARCH_HISTORY_MAX_LEN"
_SEARCH_HISTORY_MAX_LEN_DEFAULT = 50
_SEARCH_HISTORY_MAX_LEN_MIN = 10
_SEARCH_HISTORY_MAX_LEN_MAX = 200


# ─────────────────────────────────────────────────────────────────────────────
# 환경 변수 로더 — 공통 헬퍼 SSOT (하드코딩 금지)
# ─────────────────────────────────────────────────────────────────────────────

_NumT = TypeVar("_NumT", int, float)


def _parse_bounded_env_number(
    env_key: str,
    default: _NumT,
    min_val: _NumT,
    max_val: _NumT,
    parser: Callable[[str], _NumT],
) -> _NumT:
    """
    환경 변수를 안전하게 파싱하고 [min_val, max_val] 범위로 Clamp하는 SSOT 헬퍼.

    _load_cold_start_threshold와 _load_cold_start_global_weight가 이 헬퍼를
    공유해 파싱/보정 동작을 단일 지점에서 관리한다.
    특성상 int 로더는 `parser=int`, float 로더는 `parser=float`를 전달한다.

    동작 우선순위:
      1) 미설정(None)      → 조용히 기본값 반환
      2) 빈값/공백       → 운영자 오설정 의심 → WARNING + 기본값
      3) 파싱 실패       → WARNING + 기본값
      4) 비정상 부동소수점 (float 전용) → NaN·±inf 유효하지 않은 값 → WARNING + 기본값
         (이 헬퍼는 현재 int/float만 지원하며, int는 NaN/inf 자체가 불가하므로 해당 없음)
      5) 범위 이탈       → Clamp + WARNING
      6) 정상            → 파싱된 값 반환
    """
    raw = os.environ.get(env_key)

    # 1) 아예 미설정: 조용히 기본값 사용
    if raw is None:
        return default

    # 2) 설정됐으나 빈값/공백: 운영자 오설정 의심
    raw_stripped = raw.strip()
    if not raw_stripped:
        logger.warning(
            "[TOPIC_CLUSTERING] %s 가 설정됐으나 빈값/공백입니다 (운영자 오설정 의심). "
            "기본값 %r로 폴백합니다.",
            env_key,
            default,
        )
        return default

    # 3) 파싱 실패
    try:
        value = parser(raw_stripped)
    except (ValueError, TypeError):
        logger.warning(
            "[TOPIC_CLUSTERING] %s 파싱 실패 (값=%r). 기본값 %r로 폴백합니다.",
            env_key,
            raw_stripped,
            default,
        )
        return default

    # 4) 비정상 부동소수점 체크 (float 전용)
    #    NaN과 ±inf는 운영 수치로 사용할 수 없는 값으로, 서비스 측 오설정이 의심됨
    #    - NaN:  모든 비교에서 False → Clamp 바이패스 위험
    #    - ±inf: 실제 운영 수치로 유효하지 않음
    #    이 헬퍼는 현재 int/float만을 지원하며, 다른 수치 타입을 추가하려면
    #    이 체크 블록도 함께 검토해야 한다 (int는 NaN/inf 불가하므로 해당 없음)
    if isinstance(value, float) and not math.isfinite(value):
        logger.warning(
            "[TOPIC_CLUSTERING] %s 값이 비정상 부동소수점(NaN 또는 ±inf)입니다 (운영자 오설정 의심). "
            "기본값 %r로 폴백합니다.",
            env_key,
            default,
        )
        return default

    # 5) 범위 Clamp
    if value < min_val:
        logger.warning(
            "[TOPIC_CLUSTERING] %s=%r 가 최솟값(%r) 미만입니다. %r로 보정합니다.",
            env_key,
            value,
            min_val,
            min_val,
        )
        return min_val

    if value > max_val:
        logger.warning(
            "[TOPIC_CLUSTERING] %s=%r 가 최댓값(%r) 초과입니다. %r로 보정합니다.",
            env_key,
            value,
            max_val,
            max_val,
        )
        return max_val

    return value


def _load_cold_start_threshold() -> int:
    """COLD_START_THRESHOLD 환경 변수를 안전하게 파싱하고 범위를 보정한다."""
    return _parse_bounded_env_number(
        _COLD_START_THRESHOLD_ENV_KEY,
        _COLD_START_THRESHOLD_DEFAULT,
        _COLD_START_THRESHOLD_MIN,
        _COLD_START_THRESHOLD_MAX,
        int,
    )


# 모듈 로드 시 1회 계산 (런타임 환경 변수 변경은 재시작으로 반영)
_COLD_START_THRESHOLD: int = _load_cold_start_threshold()


# ─────────────────────────────────────────────────────────────────────────────
# 환경 변수 로더: Cold Start 전역 인덱스 가중치
# ─────────────────────────────────────────────────────────────────────────────


def _load_cold_start_global_weight() -> float:
    """COLD_START_GLOBAL_INDEX_WEIGHT 환경 변수를 안전하게 파싱하고 범위를 보정한다."""
    return _parse_bounded_env_number(
        _COLD_START_GLOBAL_WEIGHT_ENV_KEY,
        _COLD_START_GLOBAL_WEIGHT_DEFAULT,
        _COLD_START_GLOBAL_WEIGHT_MIN,
        _COLD_START_GLOBAL_WEIGHT_MAX,
        float,
    )


# 모듈 로드 시 1회 계산
GLOBAL_INDEX_WEIGHT_COLD_START: float = _load_cold_start_global_weight()


def _load_search_history_max_len() -> int:
    """SEARCH_HISTORY_MAX_LEN 환경 변수를 안전하게 파싱하고 범위를 보정한다."""
    return _parse_bounded_env_number(
        _SEARCH_HISTORY_MAX_LEN_ENV_KEY,
        _SEARCH_HISTORY_MAX_LEN_DEFAULT,
        _SEARCH_HISTORY_MAX_LEN_MIN,
        _SEARCH_HISTORY_MAX_LEN_MAX,
        int,
    )


# 모듈 로드 시 1회 계산
_SEARCH_HISTORY_MAX_LEN: int = _load_search_history_max_len()


# 클러스터링 캐시 TTL 설정 (환경 변수로 외부화, 기본 24시간 = 86400초)
_CLUSTER_CACHE_TTL_ENV_KEY = "TOPIC_CLUSTER_CACHE_TTL"
_CLUSTER_CACHE_TTL_DEFAULT = 86400
_CLUSTER_CACHE_TTL_MIN = 3600
_CLUSTER_CACHE_TTL_MAX = 604800  # 최대 7일


def _load_cluster_cache_ttl() -> int:
    """TOPIC_CLUSTER_CACHE_TTL 환경 변수를 파싱하고 범위를 보정한다."""
    return _parse_bounded_env_number(
        _CLUSTER_CACHE_TTL_ENV_KEY,
        _CLUSTER_CACHE_TTL_DEFAULT,
        _CLUSTER_CACHE_TTL_MIN,
        _CLUSTER_CACHE_TTL_MAX,
        int,
    )


# 모듈 로드 시 1회 계산
_TOPIC_CLUSTER_CACHE_TTL: int = _load_cluster_cache_ttl()


# 실루엣 점수 향상분 임계값 (환경 변수로 외부화)
_SIL_THRESHOLD_ENV_KEY = "SILHOUETTE_IMPROVEMENT_THRESHOLD"
_SIL_THRESHOLD_DEFAULT = 0.1
_SIL_THRESHOLD_MIN = 0.0
_SIL_THRESHOLD_MAX = 1.0


def _load_sil_threshold() -> float:
    """SILHOUETTE_IMPROVEMENT_THRESHOLD 환경 변수를 안전하게 파싱하고 범위를 보정한다."""
    return _parse_bounded_env_number(
        _SIL_THRESHOLD_ENV_KEY,
        _SIL_THRESHOLD_DEFAULT,
        _SIL_THRESHOLD_MIN,
        _SIL_THRESHOLD_MAX,
        float,
    )


# 모듈 로드 시 1회 계산
_SILHOUETTE_IMPROVEMENT_THRESHOLD: float = _load_sil_threshold()


# 실루엣 점수 샘플 상한 (환경 변수로 외부화)
_SIL_SAMPLE_SIZE_ENV_KEY = "SILHOUETTE_SAMPLE_SIZE"
_SIL_SAMPLE_SIZE_DEFAULT = 100
_SIL_SAMPLE_SIZE_MIN = 50
_SIL_SAMPLE_SIZE_MAX = 1000


def _load_sil_sample_size() -> int:
    """SILHOUETTE_SAMPLE_SIZE 환경 변수를 안전하게 파싱하고 범위를 보정한다."""
    return _parse_bounded_env_number(
        _SIL_SAMPLE_SIZE_ENV_KEY,
        _SIL_SAMPLE_SIZE_DEFAULT,
        _SIL_SAMPLE_SIZE_MIN,
        _SIL_SAMPLE_SIZE_MAX,
        int,
    )


# 모듈 로드 시 1회 계산
_SILHOUETTE_SAMPLE_SIZE: int = _load_sil_sample_size()
# ML 재현성(Idempotency) 보장을 위한 전역 시드 상수
_ML_RANDOM_STATE: int = 42

# 클러스터링 알고리즘 하이퍼파라미터 (SSOT)
_MIN_SAMPLES_FOR_CLUSTERING: int = 3
_MAX_CLUSTERS_LIMIT: int = 10
_INERTIA_FLATTEN_THRESHOLD: float = 0.05
_MIN_K_FOR_INERTIA_FLATTEN: int = 3
_MIN_FLATTEN_CONSECUTIVE_STEPS: int = 2


class ClusteringConfigError(ValueError):
    """클러스터링 알고리즘 설정값 오류 시 발생하는 도메인 특화 예외"""
    def __init__(self, message: str, param: Optional[str] = None, value: Optional[Any] = None):
        super().__init__(message)
        self.param = param
        self.value = value

    def __str__(self) -> str:
        # [리뷰반영] 확장성을 고려하여 요소들의 리스트를 조건부로 생성 후 조인(join)
        base_msg = super().__str__()
        details = []
        if self.param is not None:
            details.append(f"param={self.param}")
        if self.value is not None:
            details.append(f"value={self.value}")
        
        if details:
            return f"{base_msg} ({', '.join(details)})"
        return base_msg

    def get_log_extra(self) -> dict[str, Any]:
        """
        [리뷰반영] 구조화된 로깅(Structured Logging)을 위한 페이로드 생성.
        값이 None인 필드는 생략하여 불필요한 로그 인덱싱 자원 낭비를 방지한다.
        """
        extra: dict[str, Any] = {}
        if self.param is not None:
            extra["param"] = self.param
        if self.value is not None:
            extra["value"] = self.value
        return extra


def _assert_valid_clustering_config(
    min_k_flatten: int, min_consecutive_steps: int
) -> None:
    """
    [리뷰반영] 클러스터링 관련 설정값을 단일 진입점에서 검증하고, 잘못된 경우 커스텀 예외를 발생시킨다.

    이 함수는 모듈 레벨의 설정 상수를 인자로 주입받아 유효성을 검사하며,
    전역 상태에 직접 의존하지 않아 테스트 용이성(Testability)이 높다.
    """
    if min_k_flatten < 2:
        err = ClusteringConfigError(
            "[TOPIC_CLUSTERING] Misconfiguration: _MIN_K_FOR_INERTIA_FLATTEN must be >= 2.",
            param="_MIN_K_FOR_INERTIA_FLATTEN",
            value=min_k_flatten,
        )
        # [리뷰반영] 예외 객체 내부에 캡슐화된 메서드를 호출하여 extra kwargs 제공 (DRY)
        logger.critical(str(err), extra=err.get_log_extra())
        raise err
    
    if min_consecutive_steps < 1:
        err = ClusteringConfigError(
            "[TOPIC_CLUSTERING] Misconfiguration: _MIN_FLATTEN_CONSECUTIVE_STEPS must be >= 1.",
            param="_MIN_FLATTEN_CONSECUTIVE_STEPS",
            value=min_consecutive_steps,
        )
        # [리뷰반영] 예외 객체 내부에 캡슐화된 메서드를 호출하여 extra kwargs 제공 (DRY)
        logger.critical(str(err), extra=err.get_log_extra())
        raise err


# ─────────────────────────────────────────────────────────────────────────────
# Redis 키 빌더 (SSOT — 하드코딩 금지)
# ─────────────────────────────────────────────────────────────────────────────


def _build_msg_pair_count_key(hashed_user_id: str) -> str:
    """메시지 쌍 카운터 Redis 키를 생성한다. (변경 시 이 함수만 수정)"""
    return f"{_MSG_PAIR_COUNT_PREFIX}:{hashed_user_id}"


def _build_rag_search_count_key(hashed_user_id: str) -> str:
    """RAG 검색 카운터 Redis 키를 생성한다. (변경 시 이 함수만 수정)"""
    return f"{_RAG_SEARCH_COUNT_PREFIX}:{hashed_user_id}"


def _build_query_history_key(hashed_user_id: str) -> str:
    """검색어 히스토리 Redis 키를 생성한다. (변경 시 이 함수만 수정)"""
    return f"{_QUERY_HISTORY_PREFIX}:{hashed_user_id}"


def _build_cluster_cache_key(hashed_user_id: str) -> str:
    """클러스터링 결과 캐시 Redis 키를 생성한다. (데이터 스키마 버전 포함)"""
    version = _get_cluster_cache_version()
    return f"{_CLUSTER_CACHE_PREFIX}:{version}:{hashed_user_id}"


# ─────────────────────────────────────────────────────────────────────────────
# Redis 연결 보장 헬퍼
# ─────────────────────────────────────────────────────────────────────────────


async def _ensure_redis_connected() -> None:
    """
    Redis 연결이 끊어진 경우 재연결을 시도한다.
    일시적인 장애 시 예외를 삼키지 않고 WARNING 로그만 남기며 계속 진행한다.
    (콜드 스타트 플로우가 Redis 장애로 완전히 멈추지 않도록 Graceful Degradation)
    """
    if not redis_client.is_connected():
        try:
            await redis_client.connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[TOPIC_CLUSTERING] Redis 재연결 실패. Cold Start 조회는 기본값(0)으로 폴백합니다. exc=%r",
                exc,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Cold Start 카운터 조회 헬퍼 (MGET으로 단일 RTT 최적화)
# ─────────────────────────────────────────────────────────────────────────────


def _parse_raw_int(raw: object) -> int:
    """
    Redis raw 값을 정수로 파싱하는 SSOT 헬퍼.
    None이거나 파싱에 실패하면 0을 반환한다 (best-effort).
    _get_redis_count 및 _get_two_redis_counts 양쪽에서 재사용한다.
    """
    if raw is None:
        return 0
    try:
        return int(raw)  # type: ignore[arg-type]
    except (ValueError, TypeError) as exc:
        # [리뷰반영] 비숫자 값은 Redis 데이터 손상일 수 있으므로 DEBUG 레벨로 가시화
        logger.debug(
            "[TOPIC_CLUSTERING] Redis raw 값 파싱 실패 (raw=%r). 0으로 처리합니다. exc=%r",
            raw,
            exc,
        )
        return 0


async def _get_redis_count(key: str) -> int:
    """
    Redis 문자열 키에서 정수 카운터를 읽어 반환한다.
    키가 없거나 파싱에 실패하거나 Redis 운영 오류가 발생하면 모두 0을 반환한다.
    (Cold Start 판별은 best-effort — Redis 장애가 사용자 플로우를 막지 않아야 함)
    """
    try:
        raw = await redis_client.redis.get(key)
        return _parse_raw_int(raw)
    except RedisError as exc:  # 연결/타임아웃/명령 실패 등
        logger.warning(
            "[TOPIC_CLUSTERING] Redis 카운터 조회 실패 (key=%r). 0으로 처리합니다. exc=%r",
            key,
            exc,
        )
        return 0


async def _get_two_redis_counts(key1: str, key2: str) -> tuple[int, int]:
    """
    두 Redis 키의 정수 카운터를 MGET으로 단일 왕복(1 RTT)에 가져온다.
    Hot path에서 2번의 연속 GET 대신 MGET을 사용해 네트워크 지연을 최소화한다.
    조회 실패, 예상 외 응답(None/짧은 리스트), 파싱 실패 시 모두 0으로 처리 (best-effort).
    """
    try:
        results = await redis_client.redis.mget(key1, key2)
    except RedisError as exc:
        logger.warning(
            "[TOPIC_CLUSTERING] MGET 조회 실패 (keys=%r, %r). 0으로 처리합니다. exc=%r",
            key1,
            key2,
            exc,
        )
        return 0, 0

    # [리뷰반영] mget이 None이나 길이 부족한 리스트를 반환할 경우를 방어
    if results is None or len(results) < 2:
        logger.warning(
            "[TOPIC_CLUSTERING] MGET 응답이 예상과 다릅니다 (keys=%r, %r, results=%r). 0으로 처리합니다.",
            key1,
            key2,
            results,
        )
        return 0, 0

    # [리뷰반영] _parse_raw_int SSOT 헬퍼 재사용 (중복 파싱 로직 제거)
    return _parse_raw_int(results[0]), _parse_raw_int(results[1])


# ─────────────────────────────────────────────────────────────────────────────
# Public API: Cold Start 판별
# ─────────────────────────────────────────────────────────────────────────────


async def is_cold_start_user(
    hashed_user_id: str,
    masked_uid: Optional[str] = None,
) -> bool:
    """
    hashed_user_id 기반으로 해당 사용자가 콜드 스타트 상태인지 판별한다.

    판별 기준:
      - 메시지 쌍(Q/A) 수 + 유효 RAG 검색 수의 합산이 _COLD_START_THRESHOLD 미만

    Args:
        hashed_user_id: SHA-256 해시된 사용자 식별자 (평문 user_id 금지)
        masked_uid    : 로깅용 마스킹 식별자 (생략 시 내부에서 앞 8자리 사용)

    Returns:
        True  → 콜드 스타트 (데이터 부족, 전역 인덱스 100% 사용 권장)
        False → 정상 사용자 (클러스터링 파이프라인 진입 가능)
    """
    # [리뷰반영] 문서에 명시된 PII 정책과 일치하도록 mask_pii_id() 헬퍼를 사용
    log_uid = masked_uid or mask_pii_id(hashed_user_id)

    await _ensure_redis_connected()

    msg_pair_key = _build_msg_pair_count_key(hashed_user_id)
    rag_search_key = _build_rag_search_count_key(hashed_user_id)

    # [리뷰반영] 두 번의 연속 GET → MGET으로 단일 왕복(1 RTT) 최적화
    msg_pair_count, rag_search_count = await _get_two_redis_counts(
        msg_pair_key, rag_search_key
    )

    total_activity = msg_pair_count + rag_search_count
    is_cold = total_activity < _COLD_START_THRESHOLD

    logger.info(
        "[TOPIC_CLUSTERING][COLD_START] masked_uid=%s | "
        "msg_pairs=%d, rag_searches=%d, total=%d, threshold=%d → cold_start=%s",
        log_uid,
        msg_pair_count,
        rag_search_count,
        total_activity,
        _COLD_START_THRESHOLD,
        is_cold,
    )

    return is_cold


# ─────────────────────────────────────────────────────────────────────────────
# Public API: Cold Start 카운터 증가 (호출자가 활동 발생 시 증분)
# ─────────────────────────────────────────────────────────────────────────────


async def increment_msg_pair_count(hashed_user_id: str) -> None:
    """
    사용자의 완료된 메시지 쌍 카운터를 Redis에서 1 증가시킨다.
    챗봇 응답이 정상적으로 완료될 때마다 호출한다.

    Redis 카운터 증분은 best-effort로 처리하며,
    Redis 에러 발생 시 경고 로그만 남기고 호출자의 플로우는 계속 진행된다.
    """
    await _ensure_redis_connected()
    key = _build_msg_pair_count_key(hashed_user_id)
    try:
        await redis_client.redis.incr(key)
    except RedisError as exc:
        logger.warning(
            "[TOPIC_CLUSTERING] 메시지 쌍 카운터 증분 실패 (best-effort, 흐름 유지). exc=%r",
            exc,
        )


async def increment_rag_search_count(hashed_user_id: str) -> None:
    """
    사용자의 유효 RAG 검색 수행 카운터를 Redis에서 1 증가시킨다.
    RAG 파이프라인이 실제 결과를 반환할 때만 호출한다.

    Redis 카운터 증분은 best-effort로 처리하며,
    Redis 에러 발생 시 경고 로그만 남기고 호출자의 플로우는 계속 진행된다.
    """
    await _ensure_redis_connected()
    key = _build_rag_search_count_key(hashed_user_id)
    try:
        await redis_client.redis.incr(key)
    except RedisError as exc:
        logger.warning(
            "[TOPIC_CLUSTERING] RAG 검색 카운터 증분 실패 (best-effort, 흐름 유지). exc=%r",
            exc,
        )


def _preprocess_query(query: str) -> str:
    """
    검색어 전처리 파이프라인.
    - 소문자화 (영문)
    - 특수문자 제거
    - 연속 공백 정규화 (단일 공백)
    - 양끝 공백 제거
    """
    if not query:
        return ""

    # 1. 소문자화
    text = query.lower()

    # 2. 특수문자 제거 (안전한 문자열 확보)
    text = _CLEAN_RE.sub(" ", text)

    # 3. 연속 공백 통합 및 Trim
    text = _WS_RE.sub(" ", text).strip()

    return text


async def _invalidate_cluster_cache(hashed_user_id: str) -> None:
    """
    [리뷰반영] 캐시 무효화 책임을 분리한 내부 헬퍼.
    """
    cache_key = _build_cluster_cache_key(hashed_user_id)
    try:
        await _ensure_redis_connected()  # [리뷰반영] 캐시 조작 전 일관된 연결 보장
        await redis_client.redis.delete(cache_key)
    except RedisError as exc:
        # [리뷰반영] 여러 경로(검색, 디코딩 실패 등)에서 호출되므로 범용적인 로그 메시지 사용
        logger.warning(
            "[TOPIC_CLUSTERING] 캐시 무효화(삭제) 실패 (best-effort 무시) (masked_uid=%s). exc=%r",
            mask_pii_id(hashed_user_id),
            exc,
        )


async def log_search_query(hashed_user_id: str, query: str) -> None:
    """
    사용자의 검색 쿼리를 히스토리에 기록하고, 카운터를 1 증가시킨다.
    - 쿼리 전처리 수행 (_preprocess_query)
    - Redis List의 머리에 추가 (LPUSH)
    - 최대 길이 제한 유지 (LTRIM)

    이 모든 과정은 best-effort로 처리되며, 개별 단계의 실패가 전체 검색 흐름을 방해하지 않는다.
    """
    # 1. 전처리 (로그 기록 전 정제)
    clean_query = _preprocess_query(query)
    if not clean_query:
        return

    # [리뷰반영] _ensure_redis_connected 중복 호출 제거:
    # increment_rag_search_count 내부에서 이미 호출하므로 여기서는 불필요하다.
    # 2. 카운터 증가 (기존 로직 재사용)
    await increment_rag_search_count(hashed_user_id)

    # 3. 히스토리 리스트 추가
    history_key = _build_query_history_key(hashed_user_id)

    try:
        # LPUSH(최신 쿼리가 맨 앞) + LTRIM(최대 길이 유지) 수행
        await redis_client.redis.lpush(history_key, clean_query)
        await redis_client.redis.ltrim(history_key, 0, _SEARCH_HISTORY_MAX_LEN - 1)
    except RedisError as exc:
        logger.warning(
            "[TOPIC_CLUSTERING] 검색 히스토리 기록 실패 (masked_uid=%s). exc=%r",
            mask_pii_id(hashed_user_id),
            exc,
        )
    finally:
        # [리뷰반영] 부분적인 쓰기 성공이나 네트워크 오류 상황에서도
        # 히스토리가 변경되었을 수 있으므로 캐시 무효화는 항상 시도한다.
        await _invalidate_cluster_cache(hashed_user_id)


async def vectorize_queries(queries: List[str]) -> List[List[float]]:
    """
    히스토리 쿼리 리스트를 일괄(Batch) 벡터화한다.
    기존 EmbeddingGenerator를 재사용하며, 실패 시 빈 리스트를 반환한다.

    [리뷰반영] generate_embeddings는 동기 CPU/IO 작업으로 이벤트루프를 블로킹할 수 있다.
    run_in_threadpool로 래핑하여 asyncio 이벤트루프를 즉시 반환하고
    별도 스레드에서 임베딩 API 호출을 처리한다.

    반환 정책 (보수적):
    - generate_embeddings가 dict가 아니거나 None을 반환하면 [] 반환
    - 임베딩 수가 요청한 쿼리 수와 다르면 [] 반환 (쿼리-벡터 인덱스 불일치 방지)
    - 부분 결과는 silent bug로 이어질 수 있으므로 전부 버린다.

    Returns:
        임베딩 벡터 리스트 (성공 시 len(queries)와 동일한 길이, 실패 시 [])
    """
    if not queries:
        return []

    try:
        generator = _get_embedding_generator()
        # [리뷰반영] 동기 메서드를 run_in_threadpool로 래핑 → 이벤트루프 비차단 보장
        result = await run_in_threadpool(generator.generate_embeddings, queries)

        # [리뷰반영] result 타입 검증:
        # generate_embeddings가 예외 대신 None이나 비-dict를 반환할 경우 AttributeError를 예방한다.
        if not isinstance(result, dict):
            logger.warning(
                "[TOPIC_CLUSTERING] generate_embeddings 반환값이 dict가 아닙니다 "
                "(type=%s). 빈 리스트를 반환합니다.",
                type(result).__name__,
            )
            return []

        embeddings_raw = result.get("embeddings")

        # [리뷰반영] or [] 적용 전에 원본 값으로 타입 검증:
        # 이전: result.get("embeddings") 에 or fallback이 먼저 적용되어
        #        None·""·{} 등 falsy 계약 위반이 []로 덮여 감지 불가.
        # 수정: 원본 raw 값에서 isinstance 검사 후 → 이상 없을 때만 사용.
        if not isinstance(embeddings_raw, list):
            logger.warning(
                "[TOPIC_CLUSTERING] generate_embeddings 'embeddings' 필드가 list가 아닙니다 "
                "(type=%s). 빈 리스트를 반환합니다.",
                type(embeddings_raw).__name__,
            )
            return []

        # [리뷰반영] 벡터 요소 타입 정밀 검증 (List[List[float | int]]):
        # 껍데기만 list이고 내부 요소가 dict나 문자열 등인 잘못된 API 응답을 조기 차단한다.
        # 배열 데이터가 포함된 경우 부분적인 악성/잘못된 값이 섞여 들어오는 것을 막기 위해 모든 요소를 검증한다.
        is_valid_structure = True
        for row in embeddings_raw:
            if not isinstance(row, list):
                is_valid_structure = False
                break
            # 일부 데이터만 훼손된 경우의 silent failure 방지를 위해 전체 요소 순회 검사
            if not all(isinstance(x, (int, float)) for x in row):
                is_valid_structure = False
                break

        if not is_valid_structure:
            logger.warning(
                "[TOPIC_CLUSTERING] generate_embeddings 벡터 반환 형식이 유효한 숫자 배열(List[List[float | int]])이 아닙니다. 빈 리스트를 반환합니다."
            )
            return []

        embeddings = embeddings_raw  # 이미 list임이 보장됨 (or [] 불필요)

        # 길이 검증: 부분 실패로 인한 쿼리-벡터 인덱스 불일치 방지
        if len(embeddings) != len(queries):
            logger.warning(
                "[TOPIC_CLUSTERING] 벡터화 결과 길이 불일치 "
                "(queries=%d, embeddings=%d). 부분 결과는 무시합니다.",
                len(queries),
                len(embeddings),
            )
            return []

        return embeddings
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[TOPIC_CLUSTERING] 검색 히스토리 벡터화 실패 (count=%d). exc=%r",
            len(queries),
            exc,
        )
        return []


async def get_search_history(hashed_user_id: str) -> List[str]:
    """
    사용자의 최근 검색어 히스토리를 반환한다. (최신순)
    Redis 연결 실패를 포함하여 모든 예외를 내부에서 처리하며,
    오류 발생 시 빈 리스트를 반환한다 (best-effort).

    [리뷰반영] except 범위를 Exception으로 확장하여 docstring과 동작을 일치시킨다.
    RedisError · UnicodeDecodeError 외에도 OSError 등 예상치 못한 예외가 발생할 수 있으므로,
    모두 빈 리스트로 폐기 처리한다.

    Returns:
        검색어 리스트 (비어있을 수 있음)
    """
    history_key = _build_query_history_key(hashed_user_id)

    try:
        # [리뷰반영] _ensure_redis_connected를 try 블록 안으로 이동:
        # 연결 오류 발생 시에도 docstring대로 빈 리스트를 반환한다.
        await _ensure_redis_connected()
        raw_list = await redis_client.redis.lrange(history_key, 0, -1)
        if not raw_list:
            return []

        # Redis 응답은 bytes일 수 있으므로 디코딩
        return [q.decode("utf-8") if isinstance(q, bytes) else str(q) for q in raw_list]
    except Exception as exc:  # noqa: BLE001
        # RedisError · UnicodeDecodeError 외의 예상치 못한 예외도 조용히 폐기한다.
        logger.warning(
            "[TOPIC_CLUSTERING] 검색 히스토리 조회 실패 (masked_uid=%s). exc=%r",
            mask_pii_id(hashed_user_id),
            exc,
        )
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Public API: Cold Start 폴백 가중치 반환
# ─────────────────────────────────────────────────────────────────────────────


def get_cold_start_index_weight() -> float:
    """
    콜드 스타트 상태일 때 적용할 전역 인덱스 가중치를 반환한다.

    Returns:
        1.0 (GLOBAL_INDEX_WEIGHT=1.0, 개인화 완전 비활성화)
    """
    return GLOBAL_INDEX_WEIGHT_COLD_START


# ─────────────────────────────────────────────────────────────────────────────
# [Step 2-3 / Phase 2] Core ML: k-means 클러스터링 알고리즘 구현
# ─────────────────────────────────────────────────────────────────────────────


def _find_elbow_point(inertias: List[float], k_range: List[int]) -> int:
    """
    관성(Inertia) 배열에서 엘보우 포인트(곡률이 최대인 지점)를 찾는다.
    시작점과 끝점을 이은 직선에서 가장 멀리 떨어진 점을 선택한다.
    """
    if len(inertias) < 3:
        return k_range[0]

    p1 = np.array([k_range[0], inertias[0]])
    p2 = np.array([k_range[-1], inertias[-1]])

    distances = []
    for i, k in enumerate(k_range):
        p3 = np.array([k, inertias[i]])
        # 점 p3와 직선 p1-p2 사이의 거리 계산
        # np.cross는 2D 벡터에서 평행사변형 면적을 반환함
        dist = float(np.abs(np.cross(p2 - p1, p1 - p3)) / np.linalg.norm(p2 - p1))
        distances.append(dist)

    return int(k_range[np.argmax(distances)])


def _create_kmeans(n_clusters: int) -> KMeans:
    """
    KMeans 인스턴스 생성을 위한 중앙 집중식 팩토리 헬퍼.
    매직 넘버(random_state 등)를 한 곳에서 관리하여 일관성 및 재현성을 보장한다.
    """
    return KMeans(n_clusters=n_clusters, random_state=_ML_RANDOM_STATE, n_init="auto")


import typing

def _compute_silhouette_safe(
    embeddings: np.ndarray, labels: np.ndarray
) -> float:
    """
    [리뷰반영] 실루엣 점수 계산을 안전하게 수행하는 헬퍼 함수.
    단일 클러스터 붕괴 시 예외를 방지하고 다운샘플링을 적용한다.
    """
    if len(np.unique(labels)) <= 1:
        return -1.0

    n_samples = embeddings.shape[0]
    sample_size = (
        _SILHOUETTE_SAMPLE_SIZE if n_samples > _SILHOUETTE_SAMPLE_SIZE else None
    )
    return float(
        silhouette_score(
            embeddings,
            labels,
            sample_size=sample_size,
            random_state=_ML_RANDOM_STATE,
        )
    )


def _update_inertia_flatten_state(
    prev_inertia: float,
    current_inertia: float,
    current_k: int,
    flatten_count: int,
) -> typing.Tuple[int, bool]:
    """
    [리뷰반영] 관성 평탄화 검사 로직을 순수 헬퍼 함수로 추출.
    """
    if prev_inertia <= 0:
        return 0, False

    improvement = (prev_inertia - current_inertia) / prev_inertia

    if improvement < _INERTIA_FLATTEN_THRESHOLD:
        flatten_count += 1
    else:
        flatten_count = 0

    should_stop = flatten_count >= _MIN_FLATTEN_CONSECUTIVE_STEPS
    if should_stop:
        logger.debug(
            "[TOPIC_CLUSTERING] Inertia flattened at k=%d over %d consecutive steps, short-circuiting.",
            current_k,
            flatten_count,
        )

    return flatten_count, should_stop


def _maybe_update_inertia_flatten_state(
    inertias: List[float],
    current_k: int,
    flatten_count: int,
) -> typing.Tuple[int, bool]:
    """
    [리뷰반영] 관성(inertia) 리스트 길이 확인 및 순수 헬퍼 호출을 감싸는 래퍼.
    메인 루프에서 분기 처리를 제거하여 선형성을 유지한다.
    """
    if len(inertias) < _MIN_K_FOR_INERTIA_FLATTEN:
        # [리뷰반영] 임계값 도달 전에는 평탄화 카운트를 0으로 리셋하여 기존 순수 로직과의 동작 일관성 보장
        return 0, False

    prev_inertia, current_inertia = inertias[-2], inertias[-1]
    return _update_inertia_flatten_state(
        prev_inertia,
        current_inertia,
        current_k,
        flatten_count,
    )


def _determine_optimal_k(embeddings: np.ndarray, max_k: int = _MAX_CLUSTERS_LIMIT) -> int:
    """
    엘보우 메서드(1차)와 실루엣 계수(2차)를 활용하여 최적의 K(클러스터 수)를 결정한다.
    """
    n_samples = embeddings.shape[0]
    if n_samples < _MIN_SAMPLES_FOR_CLUSTERING:
        return 1 if n_samples > 0 else 0

    limit_k = min(n_samples - 1, max_k)
    if limit_k < 2:
        return 1

    inertias: List[float] = []
    k_values: List[int] = []
    sil_by_k: Dict[int, float] = {}  # [리뷰반영] K를 키로 실루엣을 매핑하여 O(n) 탐색 제거
    inertia_flatten_count = 0

    for k in range(2, limit_k + 1):
        kmeans = _create_kmeans(k)
        labels = kmeans.fit_predict(embeddings)
        current_inertia = float(kmeans.inertia_)
        
        inertias.append(current_inertia)
        k_values.append(k)

        # [리뷰반영] 래퍼 헬퍼를 통해 루프 내 분기를 제거하고 선형성을 극대화
        inertia_flatten_count, should_stop = _maybe_update_inertia_flatten_state(
            inertias, k, inertia_flatten_count
        )
        if should_stop:
            # 실루엣 연산을 생략하여 O(N^2) 비용 절감
            break

        sil_by_k[k] = _compute_silhouette_safe(embeddings, labels)

    elbow_k = _find_elbow_point(inertias, k_values)

    # 조기 종료가 너무 일찍 터져서 sil_by_k가 아예 비어버린 극단적 엣지 케이스 방어
    if not sil_by_k:
        return elbow_k

    best_sil_k, best_sil = max(sil_by_k.items(), key=lambda kv: kv[1])
    elbow_sil = sil_by_k.get(elbow_k)

    # 1차 엘보우를 기본으로 하되, 실루엣 점수가 현저히 좋은 K가 있다면 그걸 채택
    if elbow_sil is None:
        # elbow_k가 조기 종료로 인해 실루엣 계산에서 제외된 경우
        optimal_k = elbow_k
    elif (best_sil - elbow_sil) > _SILHOUETTE_IMPROVEMENT_THRESHOLD:
        optimal_k = best_sil_k
    else:
        optimal_k = elbow_k

    logger.info(
        "[TOPIC_CLUSTERING] 최적 K 탐색 (samples=%d): elbow_k=%d, best_sil_k=%d -> optimal_k=%d",
        n_samples,
        elbow_k,
        best_sil_k,
        optimal_k,
    )
    return optimal_k


def _extract_cluster_labels(
    kmeans: KMeans, embeddings: np.ndarray, queries: List[str]
) -> List[Optional[str]]:
    """
    각 클러스터의 센트로이드(centroid)와 가장 가까운 쿼리를 찾아 클러스터의 대표 레이블로 사용한다.
    """
    labels: List[Optional[str]] = []
    for i in range(kmeans.n_clusters):
        centroid = kmeans.cluster_centers_[i]
        # 클러스터 i에 할당된 데이터 인덱스들
        cluster_indices = np.where(kmeans.labels_ == i)[0]

        if len(cluster_indices) == 0:
            # [리뷰반영] 하드코딩된 "Unknown Topic" 문자열 제거.
            # 빈 클러스터는 None을 반환하고 상위 레이어에서 필터링하도록 위임한다.
            labels.append(None)
            continue

        cluster_embeddings = embeddings[cluster_indices]
        # L2 norm 거리 계산
        distances = np.linalg.norm(cluster_embeddings - centroid, axis=1)
        closest_idx_in_cluster = int(np.argmin(distances))
        closest_idx_in_original = int(cluster_indices[closest_idx_in_cluster])

        labels.append(queries[closest_idx_in_original])

    return labels


async def _get_cached_cluster_result(hashed_user_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    [리뷰반영] 캐시 조회를 처리하는 내부 헬퍼.
    바이트 디코딩 이슈 방어 및 PII 마스킹 로그 일관성을 보장한다.
    """
    cache_key = _build_cluster_cache_key(hashed_user_id)
    try:
        await _ensure_redis_connected()
        cached_data = await redis_client.redis.get(cache_key)
        if not cached_data:
            return None

        # [리뷰반영] redis client가 bytes를 반환할 수 있으므로 명시적 디코딩 처리
        if isinstance(cached_data, bytes):
            cached_data = cached_data.decode("utf-8")

        parsed_data = json.loads(cached_data)

        # [리뷰반영] JSON 디코딩이 완전히 성공해야만 '진짜' 캐시 히트로 인정
        logger.debug(
            "[TOPIC_CLUSTERING] 캐시 히트 (masked_uid=%s)", mask_pii_id(hashed_user_id)
        )
        return parsed_data  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        logger.warning(
            "[TOPIC_CLUSTERING] 캐시 JSON 디코딩 실패. 손상된 캐시 삭제 진행 (masked_uid=%s). exc=%r",
            mask_pii_id(hashed_user_id),
            exc,
        )
        # [리뷰반영] 파손된 캐시 삭제 로직을 _invalidate_cluster_cache 헬퍼 호출로 대체 (DRY 및 연결 보장)
        await _invalidate_cluster_cache(hashed_user_id)
        return None
    except RedisError as exc:
        logger.warning(
            "[TOPIC_CLUSTERING] 캐시 읽기 실패 (best-effort 무시) (masked_uid=%s). exc=%r",
            mask_pii_id(hashed_user_id),
            exc,
        )
        return None


async def _set_cluster_result_cache(
    hashed_user_id: str, clusters_info: List[Dict[str, Any]]
) -> None:
    """
    [리뷰반영] 캐시 저장을 처리하는 내부 헬퍼.
    """
    if not clusters_info:
        return

    cache_key = _build_cluster_cache_key(hashed_user_id)
    try:
        await _ensure_redis_connected()  # [리뷰반영] 캐시 조작 전 일관된 연결 보장
        await redis_client.redis.setex(
            cache_key,
            _TOPIC_CLUSTER_CACHE_TTL,
            json.dumps(clusters_info, ensure_ascii=False),
        )
    except RedisError as exc:
        logger.warning(
            "[TOPIC_CLUSTERING] 캐시 쓰기 실패 (best-effort 무시) (masked_uid=%s). exc=%r",
            mask_pii_id(hashed_user_id),
            exc,
        )


async def cluster_user_topics(hashed_user_id: str) -> List[Dict[str, Any]]:
    """
    [Step 2-3] 검색 히스토리를 기반으로 관심 토픽 클러스터링(k-means)을 수행한다.

    절차:
      1) 사용자 검색 히스토리 조회
      2) 쿼리 임베딩 변환
      3) 최적 K값 산출 (Elbow + Silhouette)
      4) 클러스터링 수행 및 대표 레이블(쿼리) 추출
      5) 클러스터별 가중치(크기 비율) 계산 및 내림차순 정렬 반환

    Returns:
        [{"label": "대표 쿼리", "weight": 0.5, "size": 10}, ...]
    """
    # 런타임에 설정값 정합성을 검증하고, 잘못된 경우 명시적 커스텀 예외를 발생시킴
    _assert_valid_clustering_config(
        _MIN_K_FOR_INERTIA_FLATTEN,
        _MIN_FLATTEN_CONSECUTIVE_STEPS,
    )

    # 0) 캐시 확인 (Performance) - [리뷰반영] 단일 헬퍼 호출로 응집도 향상
    cached = await _get_cached_cluster_result(hashed_user_id)
    if cached is not None:
        return cached

    # 1) 히스토리 조회
    history = await get_search_history(hashed_user_id)
    if not history:
        return []

    # 2) 임베딩 생성 (일괄)
    embeddings_list = await vectorize_queries(history)
    if not embeddings_list or len(embeddings_list) != len(history):
        return []

    # 이벤트 루프 블로킹 방지를 위해 threadpool 사용
    def _run_clustering() -> List[Dict[str, Any]]:
        embeddings = np.array(embeddings_list)
        n_samples = embeddings.shape[0]

        if n_samples < _MIN_SAMPLES_FOR_CLUSTERING:
            # 쿼리가 매우 적은 경우 첫 번째 쿼리를 대표 토픽으로 간주
            return [{"label": history[0], "weight": 1.0, "size": n_samples}]

        # 최대 클러스터 개수는 샘플 수에 비례하되 전역 상한으로 제한
        optimal_k = _determine_optimal_k(embeddings, max_k=min(_MAX_CLUSTERS_LIMIT, n_samples - 1))

        # 공통 팩토리 헬퍼를 사용하여 KMeans 초기화
        kmeans = _create_kmeans(optimal_k)
        cluster_ids = kmeans.fit_predict(embeddings)

        labels = _extract_cluster_labels(kmeans, embeddings, history)

        cluster_sizes = np.bincount(cluster_ids, minlength=optimal_k)

        clusters_info = []
        for i in range(optimal_k):
            size = int(cluster_sizes[i])
            label_text = labels[i]

            # None 레이블(빈 클러스터)은 결과에서 누락시킴
            if size == 0 or label_text is None:
                continue

            clusters_info.append(
                {
                    "label": label_text,
                    "weight": round(size / n_samples, 4),
                    "size": size,
                }
            )

        clusters_info.sort(key=lambda x: x["weight"], reverse=True)
        return clusters_info

    try:
        clusters_info = await run_in_threadpool(_run_clustering)

        logger.info(
            "[TOPIC_CLUSTERING] 클러스터링 완료 (masked_uid=%s, queries=%d, clusters=%d)",
            mask_pii_id(hashed_user_id),
            len(history),
            len(clusters_info),
        )

        # 6) 캐시 저장 (직렬화 및 TTL 적용) - [리뷰반영] 헬퍼 호출로 추상화
        await _set_cluster_result_cache(hashed_user_id, clusters_info)

        return clusters_info
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[TOPIC_CLUSTERING] 클러스터링 실행 실패 (masked_uid=%s). exc=%r",
            mask_pii_id(hashed_user_id),
            exc,
        )
        return []

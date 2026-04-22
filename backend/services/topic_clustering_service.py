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

import logging
import math
import os
import re
import typing
from typing import Callable, List, Optional, TypeVar

import redis.exceptions
from redis.exceptions import RedisError  # 연결/타임아웃/명령 실패 포괄

from backend.services.redis_pubsub import redis_client  # type: ignore[import]
from backend.utils import mask_pii_id                   # type: ignore[import]
from backend.embedding import EmbeddingGenerator        # type: ignore[import]
from fastapi.concurrency import run_in_threadpool       # type: ignore[import]

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
_WS_RE = re.compile(r"\s+")         # 연속 공백 통합

# ─────────────────────────────────────────────────────────────────────────────
# 모듈 레벨 상수 (하드코딩 금지 — 모두 여기서 중앙 관리)
# ─────────────────────────────────────────────────────────────────────────────

# Redis 키 접두사
_MSG_PAIR_COUNT_PREFIX: str = "cls:msg_pair_count"
_RAG_SEARCH_COUNT_PREFIX: str = "cls:rag_search_count"
_QUERY_HISTORY_PREFIX: str = "cls:query_history"  # 사용자 검색어 히스토리 (List)

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
            env_key, value, min_val, min_val,
        )
        return min_val

    if value > max_val:
        logger.warning(
            "[TOPIC_CLUSTERING] %s=%r 가 최댓값(%r) 초과입니다. %r로 보정합니다.",
            env_key, value, max_val, max_val,
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
            "[TOPIC_CLUSTERING] 메시지 쌍 카운터 증분 실패 (best-effort, 흐름 유지). exc=%r", exc
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
            "[TOPIC_CLUSTERING] RAG 검색 카운터 증분 실패 (best-effort, 흐름 유지). exc=%r", exc
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

        embeddings = result.get("embeddings") or []

        # [리뷰반영] embeddings 타입 검증:
        # API 오류 시 embeddings가 list가 아닌 타입을 반환하는 경우를 조기에 감지한다.
        if not isinstance(embeddings, list):
            logger.warning(
                "[TOPIC_CLUSTERING] generate_embeddings 'embeddings' 필드가 list가 아닙니다 "
                "(type=%s). 빈 리스트를 반환합니다.",
                type(embeddings).__name__,
            )
            return []

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

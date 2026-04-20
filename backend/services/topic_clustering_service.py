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
import os
import typing
from typing import Optional

from backend.services.redis_pubsub import redis_client  # type: ignore[import]
from backend.utils import mask_pii_id                   # type: ignore[import]

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 모듈 레벨 상수 (하드코딩 금지 — 모두 여기서 중앙 관리)
# ─────────────────────────────────────────────────────────────────────────────

# Redis 키 접두사
_MSG_PAIR_COUNT_PREFIX: str = "cls:msg_pair_count"
_RAG_SEARCH_COUNT_PREFIX: str = "cls:rag_search_count"

# 콜드 스타트 판별 임계값 (환경 변수로 외부화)
# COLD_START_THRESHOLD: 누적 활동 수가 이 값 미만이면 콜드 스타트로 간주
_COLD_START_THRESHOLD_ENV_KEY = "COLD_START_THRESHOLD"
_COLD_START_THRESHOLD_DEFAULT = 5
_COLD_START_THRESHOLD_MIN = 1
_COLD_START_THRESHOLD_MAX = 100

# 콜드 스타트 시 적용할 전역 인덱스 가중치 (1.0 = 100% 전역 인덱스)
GLOBAL_INDEX_WEIGHT_COLD_START: float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 환경 변수 로더 (안전한 파싱 + 보정)
# ─────────────────────────────────────────────────────────────────────────────

def _load_cold_start_threshold() -> int:
    """
    환경 변수 COLD_START_THRESHOLD를 안전하게 파싱하고 범위를 보정한다.

    - 정상 범위: [_COLD_START_THRESHOLD_MIN, _COLD_START_THRESHOLD_MAX]
    - 범위 초과 시: 경계값으로 Clamp하고 WARNING 로그 출력
    - 파싱 오류 / 미설정 시: 기본값으로 폴백하고 WARNING 로그 출력
    """
    raw = os.environ.get(_COLD_START_THRESHOLD_ENV_KEY, "").strip()
    default = _COLD_START_THRESHOLD_DEFAULT

    if not raw:
        return default

    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[TOPIC_CLUSTERING] %s 파싱 실패 (값=%r). 기본값 %d로 폴백합니다.",
            _COLD_START_THRESHOLD_ENV_KEY,
            raw,
            default,
        )
        return default

    if value < _COLD_START_THRESHOLD_MIN:
        logger.warning(
            "[TOPIC_CLUSTERING] %s=%d 가 최솟값(%d) 미만입니다. %d로 보정합니다.",
            _COLD_START_THRESHOLD_ENV_KEY,
            value,
            _COLD_START_THRESHOLD_MIN,
            _COLD_START_THRESHOLD_MIN,
        )
        return _COLD_START_THRESHOLD_MIN

    if value > _COLD_START_THRESHOLD_MAX:
        logger.warning(
            "[TOPIC_CLUSTERING] %s=%d 가 최댓값(%d) 초과입니다. %d로 보정합니다.",
            _COLD_START_THRESHOLD_ENV_KEY,
            value,
            _COLD_START_THRESHOLD_MAX,
            _COLD_START_THRESHOLD_MAX,
        )
        return _COLD_START_THRESHOLD_MAX

    return value


# 모듈 로드 시 1회 계산 (런타임 환경 변수 변경은 재시작으로 반영)
_COLD_START_THRESHOLD: int = _load_cold_start_threshold()


# ─────────────────────────────────────────────────────────────────────────────
# Redis 키 빌더 (SSOT — 하드코딩 금지)
# ─────────────────────────────────────────────────────────────────────────────

def _build_msg_pair_count_key(hashed_user_id: str) -> str:
    """메시지 쌍 카운터 Redis 키를 생성한다. (변경 시 이 함수만 수정)"""
    return f"{_MSG_PAIR_COUNT_PREFIX}:{hashed_user_id}"


def _build_rag_search_count_key(hashed_user_id: str) -> str:
    """RAG 검색 카운터 Redis 키를 생성한다. (변경 시 이 함수만 수정)"""
    return f"{_RAG_SEARCH_COUNT_PREFIX}:{hashed_user_id}"


# ─────────────────────────────────────────────────────────────────────────────
# Redis 연결 보장 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

async def _ensure_redis_connected() -> None:
    """Redis 연결이 끊어진 경우 재연결을 시도한다."""
    if not redis_client.is_connected():
        await redis_client.connect()


# ─────────────────────────────────────────────────────────────────────────────
# Cold Start 카운터 조회 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

async def _get_redis_count(key: str) -> int:
    """
    Redis 문자열 키에서 정수 카운터를 읽어 반환한다.
    키가 없거나 파싱에 실패하면 0을 반환한다.
    """
    try:
        raw = await redis_client.redis.get(key)
        if raw is None:
            return 0
        return int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[TOPIC_CLUSTERING] Redis 카운터 파싱 실패 (key=%r). 0으로 처리합니다.",
            key,
        )
        return 0


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
    log_uid = masked_uid or hashed_user_id[:8]

    await _ensure_redis_connected()

    msg_pair_key = _build_msg_pair_count_key(hashed_user_id)
    rag_search_key = _build_rag_search_count_key(hashed_user_id)

    msg_pair_count = await _get_redis_count(msg_pair_key)
    rag_search_count = await _get_redis_count(rag_search_key)

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
    """
    await _ensure_redis_connected()
    key = _build_msg_pair_count_key(hashed_user_id)
    await redis_client.redis.incr(key)


async def increment_rag_search_count(hashed_user_id: str) -> None:
    """
    사용자의 유효 RAG 검색 수행 카운터를 Redis에서 1 증가시킨다.
    RAG 파이프라인이 실제 결과를 반환할 때만 호출한다.
    """
    await _ensure_redis_connected()
    key = _build_rag_search_count_key(hashed_user_id)
    await redis_client.redis.incr(key)


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

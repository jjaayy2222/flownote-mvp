# backend/services/golden_dataset_service.py

"""
[v8.0] Phase 5 - Step 1: Golden Dataset 필터링 서비스

'좋아요(Thumbs Up)' 평가를 받은 AI 응답 데이터를 Redis에서 수집하고
품질 기준(Quality Gates)을 통과한 항목을 구조화된 FeedbackDataPoint로 반환합니다.

관련 이슈: #933
브랜치: feature/issue-933-golden-dataset
"""

import json
import logging
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Optional

from backend.services.redis_pubsub import redis_client  # type: ignore[import]
from backend.utils import mask_pii_id  # type: ignore[import]

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Redis 키 프리픽스 상수
# chat_history_service.py의 _FEEDBACK_PREFIX와 반드시 동일하게 유지해야 합니다.
# ─────────────────────────────────────────────────────────────
_FEEDBACK_PREFIX = "chat:feedback:"

# SCAN 기본 배치 크기 (Redis 권장: 한 번에 너무 많은 키를 가져오지 않도록 제한)
_DEFAULT_SCAN_BATCH_SIZE = 100


# ─────────────────────────────────────────────────────────────
# 데이터 구조체
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FeedbackDataPoint:
    """
    Redis에서 추출된 단일 '좋아요(Thumbs Up)' 피드백의 구조화된 표현.

    frozen=True: 불변(Immutable) 보장으로 set/dict key 사용 및 안전한 공유 가능.

    Attributes:
        session_id: 세션 식별자 (원본값 보존; 외부 노출 시 mask_pii_id 적용 필수)
        message_id: 해당 AI 응답의 메시지 식별자
        feedback_text: 사용자가 작성한 텍스트 피드백 (없을 경우 None)
        timestamp: ISO 8601 형식의 피드백 기록 시각 (예: "2026-04-03T15:00:00+00:00")
    """

    session_id: str
    message_id: str
    feedback_text: Optional[str]
    timestamp: str


# ─────────────────────────────────────────────────────────────
# 모듈 레벨 순수 헬퍼 함수
# ─────────────────────────────────────────────────────────────


def _decode_str(value: Any) -> str:
    """Redis 응답값이 bytes일 경우 UTF-8 디코드, 그 외에는 str 캐스팅."""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _is_valid_timestamp(raw_ts: Any) -> bool:
    """
    timestamp 값이 처리 가능한 스칼라 타입인지 검증합니다.

    주의: bool은 int의 서브클래스이므로 명시적으로 제외합니다.
    (True/False가 각각 1/0 epoch 값으로 잘못 처리되는 것을 방지)
    """
    return isinstance(raw_ts, (int, float, str)) and not isinstance(raw_ts, bool)


def _parse_feedback_meta(
    msg_id_raw: Any,
    meta_raw: Any,
) -> Optional[tuple[str, str, Optional[str], str]]:
    """
    Redis Hash의 단일 필드 (message_id, JSON 메타) 쌍을 파싱합니다.

    반환 형식:
        (message_id, rating, feedback_text, timestamp) 또는 파싱 실패 시 None

    실패 케이스 (None 반환):
        - JSON 디코딩 오류
        - timestamp가 유효하지 않은 타입이거나 빈 문자열
    """
    msg_id = _decode_str(msg_id_raw)
    meta_str = _decode_str(meta_raw)

    try:
        meta = json.loads(meta_str)
    except (JSONDecodeError, ValueError, TypeError):
        return None

    # rating: Frontend FeedbackRating Union 타입('up' | 'down' | 'none')에 맞게 검증
    raw_rating = meta.get("rating")
    rating = raw_rating if raw_rating in ("up", "down") else "none"

    # timestamp: 유효한 스칼라 타입 + 비어있지 않아야 함
    raw_ts = meta.get("timestamp")
    if not _is_valid_timestamp(raw_ts):
        return None
    ts = str(raw_ts).strip()
    if not ts:
        return None

    # feedback_text: 없거나 공백만 있으면 None 처리
    feedback_text_raw = meta.get("text")
    feedback_text: Optional[str] = None
    if feedback_text_raw:
        stripped = str(feedback_text_raw).strip()
        feedback_text = stripped if stripped else None

    return msg_id, rating, feedback_text, ts


# ─────────────────────────────────────────────────────────────
# 핵심 서비스 함수
# ─────────────────────────────────────────────────────────────


async def filter_positive_feedbacks(
    *,
    batch_size: int = _DEFAULT_SCAN_BATCH_SIZE,
) -> list[FeedbackDataPoint]:
    """
    Redis의 모든 `chat:feedback:*` 키를 논블로킹 SCAN으로 순회하여
    품질 기준을 통과한 '좋아요(Thumbs Up)' 피드백 항목을 수집합니다.

    품질 게이트 (Quality Gates):
        1. rating == "up" 인 항목만 포함 (부정/없음 제외)
        2. timestamp가 유효한 스칼라 타입이고 비어있지 않아야 함
        3. session_id와 message_id 모두 비어있지 않아야 함
        4. (session_id, message_id) 복합 키 기준으로 중복 제거

    Args:
        batch_size: Redis SCAN이 한 번에 가져올 키 수 힌트 (기본값: 100)
                    실제 반환 수는 Redis 내부 정책에 따라 다를 수 있음.

    Returns:
        list[FeedbackDataPoint]: 품질 기준을 통과한 긍정 피드백 데이터포인트 목록.
                                 순서는 Redis SCAN 탐색 순서에 따름.

    Raises:
        redis.exceptions.ConnectionError: Redis 연결 실패 시.
        Exception: 그 외 예상치 못한 Redis 오류 시.
    """
    # (session_id, message_id) 복합 키로 중복을 O(1)에 체크하기 위한 집합
    seen: set[tuple[str, str]] = set()
    results: list[FeedbackDataPoint] = []

    try:
        # Redis 연결 보장 (chat_history_service._ensure_connected와 동일한 Fail-Fast 원칙)
        if not redis_client.is_connected():
            await redis_client.connect()

        cursor = 0
        total_scanned_keys = 0
        total_skipped_parse = 0
        total_skipped_quality = 0
        total_skipped_dedup = 0

        while True:
            cursor, partial_keys = await redis_client.redis.scan(
                cursor,
                match=f"{_FEEDBACK_PREFIX}*",
                count=batch_size,
            )

            for raw_key in partial_keys:
                key_str = _decode_str(raw_key)
                session_id = key_str.removeprefix(_FEEDBACK_PREFIX)
                total_scanned_keys += 1

                # 품질 게이트 1: session_id 비어있지 않아야 함
                if not session_id:
                    logger.warning(
                        "[OBS] Empty session_id found during golden dataset scan, skipping key.",
                        extra={"key": key_str},
                    )
                    total_skipped_quality += 1
                    continue

                feedback_hash = await redis_client.redis.hgetall(key_str)

                for msg_id_raw, meta_raw in feedback_hash.items():
                    # 파싱 시도 (실패 시 None 반환)
                    parsed = _parse_feedback_meta(msg_id_raw, meta_raw)
                    if parsed is None:
                        total_skipped_parse += 1
                        continue

                    msg_id, rating, feedback_text, timestamp = parsed

                    # 품질 게이트 2: 긍정 피드백("up")만 수집
                    if rating != "up":
                        total_skipped_quality += 1
                        continue

                    # 품질 게이트 3: message_id 비어있지 않아야 함
                    if not msg_id:
                        logger.warning(
                            "[OBS] Empty message_id found in feedback hash, skipping.",
                            extra={"session_id_hash": mask_pii_id(session_id)},
                        )
                        total_skipped_quality += 1
                        continue

                    # 품질 게이트 4: (session_id, message_id) 중복 제거
                    dedup_key = (session_id, msg_id)
                    if dedup_key in seen:
                        logger.debug(
                            "Duplicate feedback entry skipped during golden dataset scan.",
                            extra={
                                "session_id_hash": mask_pii_id(session_id),
                                "message_id_hash": mask_pii_id(msg_id),
                            },
                        )
                        total_skipped_dedup += 1
                        continue
                    seen.add(dedup_key)

                    results.append(
                        FeedbackDataPoint(
                            session_id=session_id,
                            message_id=msg_id,
                            feedback_text=feedback_text,
                            timestamp=timestamp,
                        )
                    )

            # cursor가 0으로 돌아오면 전체 키 순회 완료 (Redis SCAN 종료 조건)
            if int(cursor) == 0:
                break

        logger.info(
            "[OBS] Golden dataset positive feedback filtering complete.",
            extra={
                "total_collected": len(results),
                "total_scanned_keys": total_scanned_keys,
                "skipped_parse_error": total_skipped_parse,
                "skipped_quality_gate": total_skipped_quality,
                "skipped_dedup": total_skipped_dedup,
            },
        )
        return results

    except Exception as e:
        logger.exception(
            "[OBS] Error: Failed to filter positive feedbacks from Redis during golden dataset collection.",
            extra={"error": str(e)},
        )
        raise

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
import numbers
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Optional

import redis.exceptions

from backend.services.chat_history_service import FEEDBACK_KEY_PREFIX  # type: ignore[import]
from backend.services.redis_pubsub import redis_client  # type: ignore[import]
from backend.utils import mask_pii_id  # type: ignore[import]

logger = logging.getLogger(__name__)

# _FEEDBACK_PREFIX 대신 chat_history_service의 FEEDBACK_KEY_PREFIX를 단일 진실 공급원으로 사용합니다.
# 중복 정의를 제거하여 드리프트(값 불일치) 위험을 원천 차단합니다.

# SCAN 기본 배치 크기 (Redis 권장: 한 번에 너무 많은 키를 가져오지 않도록 제한)
_DEFAULT_SCAN_BATCH_SIZE = 100
_MIN_SCAN_BATCH_SIZE = 1
_MAX_SCAN_BATCH_SIZE = 10_000


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


def _parse_feedback_meta(
    msg_id_raw: Any,
    meta_raw: Any,
) -> Optional[tuple[str, Optional[str], str]]:
    """
    Redis Hash의 단일 필드 (message_id, JSON 메타) 쌍을 파싱합니다.

    rating 체크를 헬퍼 내부에 통합하여, 호출 측 메인 루프가
    이미 긍정("up") 평가가 확인된 엔트리만 다룰 수 있도록 설계되었습니다.

    반환 형식:
        (message_id, feedback_text, timestamp) 또는 파싱 실패/비긍정 평가 시 None

    None 반환 조건:
        - JSON 디코딩 오류
        - rating != "up" (부정/없음 포함)
        - timestamp가 유효하지 않은 타입이거나 빈 문자열
    """
    # _decode_str 인라인: 별도 함수 호출 없이 직접 처리하여 호출 오버헤드 제거
    msg_id = msg_id_raw.decode("utf-8") if isinstance(msg_id_raw, bytes) else str(msg_id_raw)
    meta_str = meta_raw.decode("utf-8") if isinstance(meta_raw, bytes) else str(meta_raw)

    try:
        meta = json.loads(meta_str)
    except (JSONDecodeError, ValueError, TypeError):
        return None

    # 긍정 피드백("up")이 아닌 모든 항목은 여기서 필터링됩니다.
    # 호출 측 메인 루프는 rating 정규화("none" 등)에 대해 알 필요가 없습니다.
    if meta.get("rating") != "up":
        return None

    # timestamp: 유효한 스칼라 타입 + 비어있지 않아야 함
    # 주의: bool은 int의 서브클래스이므로 명시적으로 제외합니다.
    # (True/False가 각각 1/0 epoch 값으로 잘못 처리되는 것을 방지)
    raw_ts = meta.get("timestamp")
    if not isinstance(raw_ts, (int, float, str)) or isinstance(raw_ts, bool):
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

    return msg_id, feedback_text, ts


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
        1. rating == "up" 인 항목만 포함 (부정/없음 제외, _parse_feedback_meta 내부에서 처리)
        2. timestamp가 유효한 스칼라 타입이고 비어있지 않아야 함
        3. session_id와 message_id 모두 비어있지 않아야 함
        4. (session_id, message_id) 복합 키 기준으로 중복 제거

    Args:
        batch_size: Redis SCAN이 한 번에 가져올 키 수 힌트.
                    허용 범위: [_MIN_SCAN_BATCH_SIZE, _MAX_SCAN_BATCH_SIZE]
                    (기본값: _DEFAULT_SCAN_BATCH_SIZE = 100, 허용: 1 ~ 10,000)
                    실제 반환 수는 Redis 내부 정책에 따라 다를 수 있음.

    Returns:
        list[FeedbackDataPoint]: 품질 기준을 통과한 긍정 피드백 데이터포인트 목록.
                                 순서는 Redis SCAN 탐색 순서에 따름.

    Raises:
        ValueError: batch_size가 허용 범위를 벗어난 경우.
        redis.exceptions.ConnectionError: Redis 연결 실패 시.
        redis.exceptions.RedisError: 그 외 Redis 명령 실패 시.
    """
    # batch_size 유효성 검증: 잘못된 값으로 인한 Redis 성능 저하 방지
    # numbers.Integral 사용: int뿐 아니라 numpy.int64 등 정수형 호환 타입도 허용.
    # bool은 int의 서브클래스이며 numbers.Integral에도 포함되므로 명시적으로 제외합니다.
    if not isinstance(batch_size, numbers.Integral) or isinstance(batch_size, bool):
        raise ValueError(
            f"batch_size must be an integer, got {type(batch_size).__name__!r}."
        )
    if not (_MIN_SCAN_BATCH_SIZE <= batch_size <= _MAX_SCAN_BATCH_SIZE):
        raise ValueError(
            f"batch_size must be between {_MIN_SCAN_BATCH_SIZE} and {_MAX_SCAN_BATCH_SIZE}, "
            f"got {batch_size}."
        )
    # (session_id, message_id) 복합 키로 중복을 O(1)에 체크하기 위한 집합
    seen: set[tuple[str, str]] = set()
    results: list[FeedbackDataPoint] = []

    try:
        # Redis 연결 보장 (chat_history_service._ensure_connected와 동일한 Fail-Fast 원칙)
        if not redis_client.is_connected():
            await redis_client.connect()

        cursor = 0
        total_scanned_keys = 0
        total_skipped_parse = 0    # JSON 디코딩 오류 또는 timestamp 유효성 실패
        total_skipped_rating = 0   # rating != "up" (부정/없음 평가)
        total_skipped_quality = 0  # session_id/message_id 비어있음
        total_skipped_dedup = 0    # (session_id, message_id) 중복

        while True:
            cursor, partial_keys = await redis_client.redis.scan(
                cursor,
                match=f"{FEEDBACK_KEY_PREFIX}*",
                count=batch_size,
            )

            for raw_key in partial_keys:
                # _decode_str 인라인: 함수가 제거되었으므로 직접 디코딩
                key_str = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
                session_id = key_str.removeprefix(FEEDBACK_KEY_PREFIX)
                total_scanned_keys += 1

                # 품질 게이트 1: session_id 비어있지 않아야 함
                if not session_id:
                    # [Security] key_str에 session_id가 포함되므로 로그에 원본값을 남기지 않습니다.
                    # session_id가 비어있다는 사실 자체가 충분한 디버깅 정보입니다.
                    logger.warning(
                        "[OBS] A Redis key matching the feedback prefix had an empty session_id suffix and was skipped.",
                    )
                    total_skipped_quality += 1
                    continue

                feedback_hash = await redis_client.redis.hgetall(key_str)

                for msg_id_raw, meta_raw in feedback_hash.items():
                    # 파싱 + rating("up") 필터를 헬퍼에 위임.
                    # None 반환 = JSON 파싱 실패 OR timestamp 오류 OR rating != "up".
                    # 카운터를 분리하기 위해, rating 필터는 헬퍼 외부에서 사전 체크합니다.
                    try:
                        meta_str = meta_raw.decode("utf-8") if isinstance(meta_raw, bytes) else str(meta_raw)
                        meta_rating = json.loads(meta_str).get("rating")
                    except (JSONDecodeError, ValueError, TypeError, AttributeError):
                        meta_rating = None

                    if meta_rating != "up":
                        total_skipped_rating += 1
                        continue

                    parsed = _parse_feedback_meta(msg_id_raw, meta_raw)
                    if parsed is None:
                        total_skipped_parse += 1
                        continue

                    msg_id, feedback_text, timestamp = parsed

                    # 품질 게이트: message_id 비어있지 않아야 함
                    if not msg_id:
                        logger.warning(
                            "[OBS] Empty message_id found in feedback hash, skipping.",
                            extra={"session_id_hash": mask_pii_id(session_id)},
                        )
                        total_skipped_quality += 1
                        continue

                    # 품질 게이트: (session_id, message_id) 중복 제거
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
                "skipped_parse_error": total_skipped_parse,    # 실제 파싱/타입 오류만 집계
                "skipped_rating_gate": total_skipped_rating,   # rating != "up" 필터 수
                "skipped_quality_gate": total_skipped_quality,
                "skipped_dedup": total_skipped_dedup,
            },
        )
        return results

    except redis.exceptions.ConnectionError as e:
        # Redis 서버 연결 실패 (서버 다운, 네트워크 오류 등)
        logger.error(
            "[OBS] Redis connection error during golden dataset collection. Check Redis server availability.",
            extra={"error": str(e)},
        )
        raise
    except redis.exceptions.RedisError as e:
        # 연결은 됐지만 Redis 명령 실패 (권한 오류, 잘못된 명령 등)
        logger.error(
            "[OBS] Redis command error during golden dataset collection.",
            extra={"error": str(e)},
        )
        raise
    # 그 외 프로그래밍 오류(AttributeError, TypeError 등)는 의도적으로 catch하지 않아
    # 자동으로 bubble up되어 디버깅 가시성을 확보합니다.

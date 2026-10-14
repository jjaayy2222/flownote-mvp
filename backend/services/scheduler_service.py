# backend/services/scheduler_service.py

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.agent.error_utils import (  # type: ignore[import]
    build_meta,
    log_agent_error,
    sanitize_content_pii,
)
from backend.api.models import ChatMessage  # type: ignore[import]
from backend.config import PathConfig
from backend.services.chat_history_service import (  # type: ignore[import]
    ChatHistoryService,
    get_chat_history_service,
)
from backend.services.golden_dataset_service import (
    FeedbackDataPoint,
    filter_positive_feedbacks,
)
from backend.utils import mask_pii_id  # type: ignore[import]
from backend.utils.finetune_parser import format_finetune_message, serialize_to_jsonl

logger = logging.getLogger(__name__)

# 전역 스케줄러 인스턴스
scheduler = AsyncIOScheduler()

# 골든 데이터셋 저장 경로 (PathConfig 기반 SSOT, 하드코딩 배제)
GOLDEN_DATASET_DIR: Path = PathConfig.DATA_DIR / "golden_dataset"

# 골든 데이터셋 기본 시스템 프롬프트 상수
_DEFAULT_SYSTEM_PROMPT: str = (
    "You are a highly helpful and accurate AI assistant. "
    "This is an automatically extracted golden dataset."
)
_FALLBACK_ANSWER_TEXT: str = "Positive AI response"


async def _resolve_qa_context(
    fb: FeedbackDataPoint,
    chat_history_service: Optional[ChatHistoryService] = None,
    session_cache: Optional[dict[str, list[ChatMessage]]] = None,
) -> tuple[str, str, bool]:
    """
    피드백 데이터포인트(session_id, message_id)를 기반으로
    ChatHistory와 조인하여 실제 사용자 질문(Q)과 AI 응답(A)을 복원합니다.

    보안 정책:
        - fb.message_id가 없거나 history에서 일치하는 assistant 메시지를 찾지 못하면
          다른 메시지로 대체(fallback)하지 않고 was_joined=False를 반환합니다.
          (데이터 오염 방지: 다른 사용자 세션의 Q/A가 골든 데이터셋에 유입되는 것을 방지)
        - turn_id가 둘 다 존재하이 서로 일치하는 user 메시지를 질문으로 선택합니다.
          turn_id가 없으면 assistant 보다 앞에 있는 user 메시지를 fallback으로 선택합니다.
        - 연결할 user 메시지가 없으면 was_joined=False 반환 (피드백 텍스트를 가짜 질문으로 사용하지 않음)
        - 복원된 모든 텍스트는 콘텐츠 레벨 PII 마스킹을 적용합니다.

    Returns:
        tuple[question, answer, was_joined]:
            - question: 복원된 사용자 질문 (복원 실패 시 빈 문자열)
            - answer: 복원된 AI 응답 (복원 실패 시 빈 문자열)
            - was_joined: 실제 ChatHistory 조인 성공 여부 (True/False)
    """
    if not fb or not fb.session_id or not fb.session_id.strip():
        return "", "", False

    # fb.message_id가 비어 있으면 정확 매칭 불가 → 짆접 실패 (fallback 금지)
    if not fb.message_id or not fb.message_id.strip():
        logger.debug(
            "[OBS] _resolve_qa_context: empty message_id for session %s, skipping.",
            mask_pii_id(fb.session_id),
        )
        return "", "", False

    # ChatHistoryService 인스턴스 확보
    history_service = chat_history_service or get_chat_history_service()

    # 세션 히스토리 조회 (배치 내 세션 캐시 활용)
    history: list[ChatMessage] = []
    if session_cache is not None and fb.session_id in session_cache:
        history = session_cache[fb.session_id]
    else:
        try:
            history = await history_service.get_history(fb.session_id, limit=50)
            if session_cache is not None:
                session_cache[fb.session_id] = history
        except Exception as exc:
            logger.debug(
                "[OBS] Failed to retrieve chat history for session %s: %s",
                mask_pii_id(fb.session_id),
                str(exc),
            )
            return "", "", False

    if not history:
        return "", "", False

    matched_idx: Optional[int] = None

    # 1순위: message_id 정확 매칭 (fallback 없음 — 보안 정책)
    # 다른 사용자 세션의 데이터가 조작된 message_id로 유입되는 것을 방지합니다.
    for idx, msg in enumerate(history):
        if (
            getattr(msg, "role", None) == "assistant"
            and getattr(msg, "message_id", None) == fb.message_id.strip()
        ):
            matched_idx = idx
            break

    if matched_idx is None:
        # 정확 매칭 실패 — 다른 메시지로 fallback 하지 않고 바로 실패 련턴
        logger.debug(
            "[OBS] _resolve_qa_context: message_id %s not found in history for session %s.",
            mask_pii_id(fb.message_id),
            mask_pii_id(fb.session_id),
        )
        return "", "", False

    matched_assistant = history[matched_idx]
    ans_content = getattr(matched_assistant, "content", None)
    if not ans_content or not str(ans_content).strip():
        return "", "", False

    resolved_a = str(ans_content).strip()

    # 사용자 질문 복원: turn_id 기반 매칭 (Comment 6 대응)
    # 동시 스트림이 같은 세션에 동시 저장되더라도 올바른 Q를 가리킵니다.
    resolved_q: Optional[str] = None
    assistant_turn_id = getattr(matched_assistant, "turn_id", None)

    if assistant_turn_id and assistant_turn_id.strip():
        # turn_id가 있으면: 같은 turn_id를 가진 user 메시지를 직접 검색
        for msg in history:
            if (
                getattr(msg, "role", None) == "user"
                and getattr(msg, "turn_id", None) == assistant_turn_id.strip()
            ):
                q_candidate = getattr(msg, "content", None)
                if q_candidate and str(q_candidate).strip():
                    resolved_q = str(q_candidate).strip()
                    break
    else:
        # turn_id가 없으면 (활성 전 데이터): assistant 직전의 user 메시지 fallback
        for idx in reversed(range(0, matched_idx)):
            if getattr(history[idx], "role", None) == "user":
                q_candidate = getattr(history[idx], "content", None)
                if q_candidate and str(q_candidate).strip():
                    resolved_q = str(q_candidate).strip()
                    break

    if not resolved_q:
        # 연결할 질문이 없으면 조인 실패 — 피드백 텍스트를 가짜 질문으로 대체하지 않음 (Comment 5)
        logger.debug(
            "[OBS] _resolve_qa_context: no user question found for assistant at idx %d (session %s).",
            matched_idx,
            mask_pii_id(fb.session_id),
        )
        return "", "", False

    # 콘텐츠 레벨 PII 마스킹 적용 (Comment 1) — 모든 텍스트를 파인튜닝 제공사에 보내기 전에 수정
    sanitized_q = sanitize_content_pii(resolved_q)
    sanitized_a = sanitize_content_pii(resolved_a)

    return sanitized_q, sanitized_a, True


async def extract_and_serialize_golden_dataset():
    """
    일 1회 빈도로 실행되는 자동 추출 작업(배치).
    Redis에서 '좋아요(Thumbs Up)' 피드백을 수집하고 실제 ChatHistory와 조인하여
    OpenAI Fine-tuning 포맷으로 변환한 뒤, 날짜별 jsonl 파일로 저장합니다.
    """
    logger.info("[OBS] Starting daily golden dataset extraction job...")

    # date_str을 try 블록 외부에서 초기화하여 except 절에서도 참조 가능하도록 보장
    date_str: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        # 1. 긍정 피드백 데이터 수집
        feedbacks = await filter_positive_feedbacks()

        if not feedbacks:
            logger.info(
                "[OBS] No positive feedbacks found today. Skipping JSONL serialization."
            )
            return

        # 2. OpenAI Chat Fine-tuning 포맷으로 구조화 (ChatHistory 조인 적용)
        dataset = []
        session_cache: dict[str, list[ChatMessage]] = {}
        joined_count = 0
        fallback_count = 0
        skipped_unmatched = 0  # message_id 불일치 또는 조인 실패로 제외된 건수

        for fb in feedbacks:
            if not fb:
                continue

            # ChatHistory 조인 및 콘텍스트 복원
            q_text, a_text, was_joined = await _resolve_qa_context(
                fb, session_cache=session_cache
            )
            if was_joined:
                joined_count += 1
            else:
                # 조인 실패 레코드는 골든 데이터셋에 입력하지 않음 (Comments 2, 3, 5)
                # 부정확한 Q/A가 파인튜닝 데이터에 포함되는 것을 방지합니다.
                skipped_unmatched += 1
                continue

            # 콘텐츠 레벨 PII 마스킹: 피드백 텍스트도 수정 (Comment 1)
            sanitized_feedback_text = (
                sanitize_content_pii(fb.feedback_text) if fb.feedback_text else None
            )

            messages = format_finetune_message(
                question=q_text,
                answer=a_text,
                system_prompt=_DEFAULT_SYSTEM_PROMPT,
            )

            # 메타데이터 분리 (PII 마스킹 대상 필드는 별도 관리)
            entry: dict = {
                **messages,
                "session_id": fb.session_id,
                "message_id": fb.message_id,
            }
            if sanitized_feedback_text:
                entry["feedback_text"] = sanitized_feedback_text

            dataset.append(entry)

        # 3. 저장 디렉토리 및 파일 경로 구성 (PathConfig 기반 SSOT)
        output_dir = GOLDEN_DATASET_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        output_filepath = str(output_dir / f"{date_str}.jsonl")

        # 4. JSONL 파일로 직렬화 (finetune_parser 모듈 활용)
        saved_path = serialize_to_jsonl(
            dataset=dataset,
            output_filepath=output_filepath,
            pii_fields=["session_id", "user_id", "message_id"],
            strict_alert=True,
        )

        logger.info(
            "[OBS] Daily golden dataset extraction completed successfully.",
            extra={
                "filename": Path(saved_path).name,
                "dataset_size": len(dataset),
                "joined_count": joined_count,
                "skipped_unmatched": skipped_unmatched,
                "date": date_str,
            },
        )

    except asyncio.CancelledError:
        # 비동기 취소 신호는 반드시 재발생시켜 스케줄러 루프가 올바르게 종료될 수 있도록 함
        raise
    except (RuntimeError, ValueError, TypeError, OSError) as e:
        meta = build_meta(
            {"action": "extract_and_serialize_golden_dataset", "date": date_str}
        )
        log_agent_error(logger, "Daily golden dataset extraction job failed", e, meta)


SENSITIVE_ENV_KEYWORDS = ("SECRET", "PASSWORD", "KEY", "TOKEN")


def _log_env_fallback(
    key: str, reason: str, default_val: Any, raw_val: Optional[str] = None
):
    """환경 변수 검증 실패 시 호출되는 로깅 헬퍼. 민감 정보는 마스킹 처리하여 안전하게 로깅합니다."""
    safe_val = (
        "***REDACTED***"
        if raw_val is not None
        and any(sec in key.upper() for sec in SENSITIVE_ENV_KEYWORDS)
        else raw_val
    )

    val_msg = f" (provided: '{safe_val}')" if safe_val is not None else ""
    logger.warning(
        "[OBS] Environment variable '%s' %s%s. Falling back to default %s.",
        key,
        reason,
        val_msg,
        default_val,
    )


def parse_env_int(key: str, default: int, min_val: int, max_val: int) -> int:
    """환경 변수에서 정수값을 안전하게 추출하고, 실패 시 기본값으로 폴백합니다."""
    if not key or not isinstance(key, str):
        return default

    val = os.environ.get(key)

    # 환경 변수가 아예 설정되지 않은 경우는 조용히 기본값 사용
    if val is None:
        return default

    # 빈 문자열 등 공백만 있는 경우, 설정 실수이므로 경고 로깅
    if not val.strip():
        _log_env_fallback(key, "is an empty string", default)
        return default

    try:
        parsed = int(val)
        if min_val <= parsed <= max_val:
            return parsed
        _log_env_fallback(
            key, f"is out of range ({min_val}-{max_val})", default, raw_val=val
        )
    except ValueError:
        _log_env_fallback(key, "is invalid", default, raw_val=val)

    return default


def start_scheduler():
    """
    APScheduler를 시작하고 예약된 작업들을 등록합니다.
    (FastAPI lifespan 이벤트 등에서 1회 호출)
    """

    # 환경 변수에서 실행 시간 및 타임존을 불러와 유연성 확보 (기본값: UTC 03:00)
    cron_hour = parse_env_int("GOLDEN_DATASET_CRON_HOUR", 3, 0, 23)
    cron_minute = parse_env_int("GOLDEN_DATASET_CRON_MINUTE", 0, 0, 59)
    cron_timezone_name = os.environ.get("GOLDEN_DATASET_CRON_TIMEZONE", "UTC")

    # 타임존 문자열을 검증/정규화하고, 실패 시 기본값(UTC)으로 폴백
    try:
        cron_timezone = ZoneInfo(
            cron_timezone_name.strip() if cron_timezone_name else "UTC"
        )
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(
            "[OBS] Timezone '%s' is invalid. Falling back to UTC.", cron_timezone_name
        )
        cron_timezone = ZoneInfo("UTC")

    scheduler.add_job(
        extract_and_serialize_golden_dataset,
        CronTrigger(hour=cron_hour, minute=cron_minute, timezone=cron_timezone),
        id="daily_golden_dataset_extractor",
        replace_existing=True,
    )

    if not scheduler.running:
        scheduler.start()
        logger.info(
            "[OBS] APScheduler started. Registered background jobs: [%s]",
            ", ".join([job.id for job in scheduler.get_jobs()]),
        )
    else:
        logger.info(
            "[OBS] APScheduler is already running. Jobs updated: [%s]",
            ", ".join([job.id for job in scheduler.get_jobs()]),
        )


def shutdown_scheduler():
    """
    서버 종료 시 스케줄러를 우아하게 종료합니다.
    """
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler shutdown gracefully.")

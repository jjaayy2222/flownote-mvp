# backend/services/scheduler_service.py

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.services.golden_dataset_service import filter_positive_feedbacks
from backend.utils.finetune_parser import format_finetune_message, serialize_to_jsonl

logger = logging.getLogger(__name__)

# 전역 스케줄러 인스턴스
scheduler = AsyncIOScheduler()


async def extract_and_serialize_golden_dataset():
    """
    일 1회 빈도로 실행되는 자동 추출 작업(배치).
    Redis에서 '좋아요(Thumbs Up)' 피드백을 모아 OpenAI Fine-tuning 포맷으로 변환한 뒤,
    날짜별 jsonl 파일로 저장합니다.
    """
    logger.info("[OBS] Starting daily golden dataset extraction job...")

    try:
        # 1. 긍정 피드백 데이터 수집
        feedbacks = await filter_positive_feedbacks()

        if not feedbacks:
            logger.info(
                "[OBS] No positive feedbacks found today. Skipping JSONL serialization."
            )
            return

        # 2. OpenAI Chat Fine-tuning 포맷으로 구조화
        dataset = []
        for fb in feedbacks:
            # TODO: 차후에 session_id와 message_id를 통해 실제 ChatHistory와 조인하여
            # 정확한 Question(Q)과 Answer(A) 컨텍스트를 구성해야 합니다.
            # 지금은 아키텍처 관점에서 스케줄러와 직렬화 파이프라인의 연결을 최우선으로 합니다.
            
            # PII 마스킹 시스템이 정상 작동하도록 민감한 식별자들을 자유 형식 텍스트(q_text, a_text)에
            # 하드코딩하지 않고, 별도의 구조화된 필드로 분리합니다.
            q_text = f"Feedback: {fb.feedback_text or 'No text'}"
            a_text = "Positive AI response"

            message_format = format_finetune_message(
                question=q_text,
                answer=a_text,
                system_prompt="You are a highly helpful and accurate AI assistant. This is an automatically extracted golden dataset.",
            )
            
            # 메타데이터 분리 추가 (pii_fields 필터링 대상)
            message_format["session_id"] = fb.session_id
            message_format["message_id"] = fb.message_id
            
            dataset.append(message_format)

        # 3. YYYY-MM-DD 를 이용한 저장 경로 생성
        now_dt = datetime.now(timezone.utc)
        date_str = now_dt.strftime("%Y-%m-%d")

        # 프로젝트 최상단 디렉토리 구조 파악 (pathlib 활용)
        project_root = Path(__file__).resolve().parent.parent.parent
        output_dir = project_root / "data" / "golden_dataset"
        
        # 디렉토리가 존재하지 않을 경우 안전하게 생성 (parents=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_filepath = str(output_dir / f"{date_str}.jsonl")

        # 4. JSONL 파일로 직렬화 (finetune_parser 모듈 활용)
        # strict_alert=True를 주어 변환 중 실패 타입이 생기면 운영 알람을 보내도록 함
        saved_path = serialize_to_jsonl(
            dataset=dataset,
            output_filepath=output_filepath,
            pii_fields=["session_id", "user_id", "message_id"],
            strict_alert=True,
        )

        logger.info(
            "[OBS] Daily golden dataset extraction completed successfully.",
            extra={
                "filepath": saved_path,
                "dataset_size": len(dataset),
                "date": date_str,
            },
        )

    except Exception as e:
        logger.error(
            "[OBS] Failed to execute daily golden dataset extraction job.",
            extra={"error": str(e)},
            exc_info=True,
        )


SENSITIVE_ENV_KEYWORDS = {"SECRET", "PASSWORD", "KEY", "TOKEN"}


def _log_env_fallback(key: str, reason: str, default_val: Any, raw_val: str = None):
    """환경 변수 검증 실패 시 호출되는 로깅 헬퍼. 민감 정보는 마스킹 처리하여 안전하게 로깅합니다."""
    safe_val = raw_val
    if raw_val is not None:
        if any(sec in key.upper() for sec in SENSITIVE_ENV_KEYWORDS):
            safe_val = "***REDACTED***"
            
    val_msg = f" (provided: '{safe_val}')" if safe_val is not None else ""
    logger.warning(
        "[OBS] Environment variable '%s' %s%s. Falling back to default %s.", 
        key, reason, val_msg, default_val
    )


def parse_env_int(key: str, default: int, min_val: int, max_val: int) -> int:
    """환경 변수에서 정수값을 안전하게 추출하고, 실패 시 기본값으로 폴백합니다."""
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
        _log_env_fallback(key, f"is out of range ({min_val}-{max_val})", default, raw_val=val)
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
        cron_timezone = ZoneInfo(cron_timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning("[OBS] Timezone '%s' is invalid. Falling back to UTC.", cron_timezone_name)
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

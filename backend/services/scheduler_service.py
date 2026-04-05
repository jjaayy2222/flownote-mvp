# backend/services/scheduler_service.py

import logging
import os
from datetime import datetime, timezone

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

        # 프로젝트 최상단 디렉토리 기준 data/golden_dataset
        # (만약 backend/ 내부에 저장하려면 경로 수정 필요)
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        output_filepath = os.path.join(
            project_root, "data", "golden_dataset", f"{date_str}.jsonl"
        )

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


def start_scheduler():
    """
    APScheduler를 시작하고 예약된 작업들을 등록합니다.
    (FastAPI lifespan 이벤트 등에서 1회 호출)
    """
    # 일 1회 실행: 매일 새벽 3시 정각에 실행 (UTC 기준)
    scheduler.add_job(
        extract_and_serialize_golden_dataset,
        CronTrigger(hour=3, minute=0, timezone="UTC"),
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

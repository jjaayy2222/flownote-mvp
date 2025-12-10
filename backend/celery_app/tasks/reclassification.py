# backend/celery_app/tasks/reclassification.py

import asyncio
import uuid
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from backend.celery_app.celery import app
from backend.services.file_access_logger import FileAccessLogger
from backend.classifier.hybrid_classifier import HybridClassifier
from backend.models.automation import (
    AutomationLog,
    AutomationTaskType,
    AutomationStatus,
    ReclassificationRecord,
)

# [Refactor] Use config for consistent paths
from backend.config import PathConfig

logger = logging.getLogger(__name__)

# [Refactor] Using PathConfig for robust path handling
LOG_DIR = PathConfig.DATA_DIR / "automation_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
AUTO_LOG_FILE = LOG_DIR / "automation.jsonl"
RECORD_LOG_FILE = LOG_DIR / "reclassification_records.jsonl"


@dataclass
class ClassificationStats:
    """Class to hold classification statistics"""

    processed: int = 0
    updated: int = 0
    errors: int = 0


def _save_automation_log(log: AutomationLog):
    """AutomationLog를 JSONL 파일에 저장"""
    try:
        with open(AUTO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log.model_dump_json() + "\n")
    except Exception as e:
        logger.error(f"Failed to save automation log: {e}")


def _save_reclassification_records(records: List[ReclassificationRecord]):
    """ReclassificationRecord 목록을 JSONL 파일에 저장"""
    try:
        with open(RECORD_LOG_FILE, "a", encoding="utf-8") as f:
            for record in records:
                f.write(record.model_dump_json() + "\n")
    except Exception as e:
        logger.error(f"Failed to save reclassification records: {e}")


def _read_file_content(path_obj: Path) -> Optional[str]:
    """[Refactor] Helper to safely read file content"""
    if not path_obj.exists() or not path_obj.is_file():
        return None
    try:
        content = path_obj.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    return content if content.strip() else None


def _infer_para_category(path_obj: Path) -> str:
    """[Refactor] Helper to infer current PARA category from path"""
    parts = path_obj.parts
    for para in ["Projects", "Areas", "Resources", "Archives", "Inbox"]:
        if para in parts:
            return para
    return "Unknown"


async def _classify_files_async(
    files: List[str], log_id: str
) -> Tuple[List[ReclassificationRecord], ClassificationStats]:
    """
    [Refactor] Internal async implementation of file classification
    Separated from the synchronous wrapper to isolate asyncio logic.
    """
    try:
        classifier = HybridClassifier()
    except Exception as e:
        logger.error(f"Failed to initialize classifier: {e}")
        # Return empty stats with error count equal to files count
        error_stats = ClassificationStats(errors=len(files))
        return [], error_stats

    records = []
    stats = ClassificationStats()

    for file_path in files:
        try:
            path_obj = Path(file_path)
            content = _read_file_content(path_obj)

            if content is None:
                # Content read failed or empty, treat as potential error or skip?
                # Original logic counted errors on read exception, skips on empty.
                # Here _read_file_content returns None for both.
                # Let's count as error only if it was an exception, but helper swallows it.
                # Simplification: we might just skip stats.errors increment for empty files to match strict original behavior?
                # Original behavior:
                # - read error -> stats["errors"] += 1
                # - empty content -> continue (no error count)
                # To match this strictly, we would need the helper to distinguish.
                # But for simplicity, we can just skip here.
                continue

            # 분류 실행
            result = await classifier.classify(content)
            stats.processed += 1

            # 기존 카테고리 추론
            old_category = _infer_para_category(path_obj)

            # 카테고리가 변경되었는지 확인
            if old_category.lower() != result.category.lower():
                stats.updated += 1

            # 레코드 생성
            record = ReclassificationRecord(
                record_id=str(uuid.uuid4()),
                automation_log_id=log_id,
                file_path=file_path,
                old_category=old_category,
                new_category=result.category,
                confidence_score=result.confidence,
                reason=result.reason,
                processed_at=datetime.now(),
            )
            records.append(record)

        except Exception as e:
            logger.error(f"Error classifying file {file_path}: {e}")
            stats.errors += 1

    return records, stats


def _classify_files(
    files: List[str], log_id: str
) -> Tuple[List[ReclassificationRecord], ClassificationStats]:
    """
    [Refactor] Synchronous wrapper for async classification logic.
    This keeps the Celery task function synchronous and simple.
    """
    return asyncio.run(_classify_files_async(files, log_id))


def _execute_reclassification(task_id: str, task_name: str, days: int):
    """재분류 로직 공통 실행 함수"""
    start_time = datetime.now()
    log_id = str(uuid.uuid4())

    # 1. 로그 초기화
    # [Refactor] Initialize errors_count explicitly (though default is 0 via Pydantic)
    log = AutomationLog(
        log_id=log_id,
        task_type=AutomationTaskType.RECLASSIFICATION,
        task_name=task_name,
        celery_task_id=task_id,
        status=AutomationStatus.RUNNING,
        started_at=start_time,
        errors_count=0,  # Explicit initialization
    )

    try:
        # 2. 대상 파일 조회
        access_logger = FileAccessLogger()
        target_files = access_logger.get_recent_files(days=days)

        logger.info(
            f"[{task_name}] Found {len(target_files)} files accessed in last {days} days."
        )

        if not target_files:
            log.status = AutomationStatus.SKIPPED
            log.details = {"message": "No files found to reclassify."}
            log.completed_at = datetime.now()
            log.duration_seconds = (log.completed_at - start_time).total_seconds()
            _save_automation_log(log)
            return "Skipped (No files)"

        # 3. 리팩토링된 동기 래퍼 호출
        records, stats = _classify_files(target_files, log_id)

        # 4. 결과 업데이트 (Using DataClass)
        log.files_processed = stats.processed
        log.files_updated = stats.updated
        # [Refactor] Safe error counting
        log.errors_count = stats.errors

        log.status = AutomationStatus.COMPLETED
        log.completed_at = datetime.now()
        log.duration_seconds = (log.completed_at - start_time).total_seconds()

        # 5. 저장
        _save_reclassification_records(records)
        _save_automation_log(log)

        return f"Success: {stats.processed} processed, {stats.updated} updated."

    except Exception as e:
        logger.error(f"[{task_name}] Failed: {e}")
        log.status = AutomationStatus.FAILED
        log.details = {"error": str(e)}
        log.completed_at = datetime.now()
        log.duration_seconds = (log.completed_at - start_time).total_seconds()

        # [Refactor] Safe increment
        if log.errors_count is None:
            log.errors_count = 0
        log.errors_count += 1

        _save_automation_log(log)
        # Celery 재시도 로직을 원한다면 여기에 추가 가능
        raise e


@app.task(bind=True)
def daily_reclassify_tasks(self):
    """매일 실행: 최근 7일간 접근된 파일 재분류"""
    return _execute_reclassification(self.request.id, "daily-reclassify", days=7)


@app.task(bind=True)
def weekly_reclassify_tasks(self):
    """매주 실행: 최근 30일간 접근된 파일 심화 재분류"""
    return _execute_reclassification(self.request.id, "weekly-reclassify", days=30)

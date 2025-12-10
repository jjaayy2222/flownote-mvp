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
from backend.config import PathConfig

logger = logging.getLogger(__name__)

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


def _read_file_content(path_obj: Path) -> Tuple[Optional[str], bool]:
    """
    Helper to safely read file content.

    Returns:
        (content or None, had_error)
        - If had_error is True, content is None and an error occurred
        - If had_error is False and content is None, file was empty
        - If had_error is False and content is not None, read succeeded
    """
    if not path_obj.exists() or not path_obj.is_file():
        logger.warning(f"File not found or not a file: {path_obj}")
        return None, True

    try:
        content = path_obj.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"Failed to read file {path_obj}: {e}")
        return None, True

    if not content.strip():
        return None, False

    return content, False


def _infer_para_category(path_obj: Path) -> str:
    """Helper to infer current PARA category from path"""
    parts = path_obj.parts
    for para in ["Projects", "Areas", "Resources", "Archives", "Inbox"]:
        if para in parts:
            return para
    return "Unknown"


async def _classify_files_async(
    files: List[str], log_id: str
) -> Tuple[List[ReclassificationRecord], ClassificationStats]:
    """
    Async implementation of file classification.

    Args:
        files: List of file paths to classify
        log_id: Automation log ID for tracking

    Returns:
        Tuple of (records, stats)
    """
    try:
        classifier = HybridClassifier()
    except Exception as e:
        logger.error(f"Failed to initialize classifier: {e}")
        return [], ClassificationStats(errors=len(files))

    records = []
    stats = ClassificationStats()

    for file_path in files:
        try:
            path_obj = Path(file_path)
            content, had_error = _read_file_content(path_obj)

            if had_error:
                stats.errors += 1
                continue

            if content is None:
                continue

            result = await classifier.classify(content)
            stats.processed += 1

            old_category = _infer_para_category(path_obj)

            if old_category.lower() != result.category.lower():
                stats.updated += 1

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


def _execute_reclassification(task_id: str, task_name: str, days: int):
    """재분류 로직 공통 실행 함수"""
    start_time = datetime.now()
    log_id = str(uuid.uuid4())

    log = AutomationLog(
        log_id=log_id,
        task_type=AutomationTaskType.RECLASSIFICATION,
        task_name=task_name,
        celery_task_id=task_id,
        status=AutomationStatus.RUNNING,
        started_at=start_time,
    )

    try:
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

        records, stats = asyncio.run(_classify_files_async(target_files, log_id))

        log.files_processed = stats.processed
        log.files_updated = stats.updated
        log.errors_count = stats.errors

        log.status = AutomationStatus.COMPLETED
        log.completed_at = datetime.now()
        log.duration_seconds = (log.completed_at - start_time).total_seconds()

        _save_reclassification_records(records)
        _save_automation_log(log)

        return f"Success: {stats.processed} processed, {stats.updated} updated."

    except Exception as e:
        logger.error(f"[{task_name}] Failed: {e}")
        log.status = AutomationStatus.FAILED
        log.details = {"error": str(e)}
        log.completed_at = datetime.now()
        log.duration_seconds = (log.completed_at - start_time).total_seconds()
        log.errors_count += 1

        _save_automation_log(log)
        raise e


@app.task(bind=True)
def daily_reclassify_tasks(self):
    """매일 실행: 최근 7일간 접근된 파일 재분류"""
    return _execute_reclassification(self.request.id, "daily-reclassify", days=7)


@app.task(bind=True)
def weekly_reclassify_tasks(self):
    """매주 실행: 최근 30일간 접근된 파일 심화 재분류"""
    return _execute_reclassification(self.request.id, "weekly-reclassify", days=30)

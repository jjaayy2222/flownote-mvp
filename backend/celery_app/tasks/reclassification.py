# backend/celery_app/tasks/reclassification.py

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from backend.agent.error_utils import build_meta, is_system_error, log_agent_error
from backend.celery_app.celery import app
from backend.classifier.hybrid_classifier import HybridClassifier
from backend.config import PathConfig
from backend.models.automation import (
    AutomationLog,
    AutomationStatus,
    AutomationTaskType,
    ReclassificationRecord,
)
from backend.services.file_access_logger import FileAccessLogger

logger = logging.getLogger(__name__)

LOG_DIR = PathConfig.DATA_DIR / "automation_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
AUTO_LOG_FILE = LOG_DIR / "automation.jsonl"
RECORD_LOG_FILE = LOG_DIR / "reclassification_records.jsonl"


@dataclass
class ReclassificationResult:
    """개별 파일 재분류 처리 결과"""

    record: Optional[ReclassificationRecord] = None
    is_error: bool = False
    is_updated: bool = False


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
    except OSError as exc:
        meta = build_meta(
            {"action": "save_automation_log"}, log_id=getattr(log, "log_id", None)
        )
        log_agent_error(logger, "Failed to save automation log", exc, meta)


def _save_reclassification_records(records: List[ReclassificationRecord]):
    """ReclassificationRecord 목록을 JSONL 파일에 저장"""
    try:
        with open(RECORD_LOG_FILE, "a", encoding="utf-8") as f:
            for record in records:
                f.write(record.model_dump_json() + "\n")
    except OSError as exc:
        meta = build_meta(
            {"action": "save_reclassification_records"}, count=len(records)
        )
        log_agent_error(logger, "Failed to save reclassification records", exc, meta)


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
    except OSError as exc:
        meta = build_meta({"action": "read_file_content"}, file_path=path_obj.name)
        log_agent_error(logger, f"Failed to read file {path_obj.name}", exc, meta)
        return None, True

    if not content.strip():
        return None, False

    return content, False


def _infer_para_category(path_obj: Path) -> str:
    """Helper to infer current PARA category from path"""
    parts = path_obj.parts
    return next(
        (
            para
            for para in ["Projects", "Areas", "Resources", "Archives", "Inbox"]
            if para in parts
        ),
        "Unknown",
    )


async def _reclassify_file(
    file_path: str, log_id: str, classifier: HybridClassifier
) -> ReclassificationResult:
    """
    Helper to reclassify a single file.

    Returns:
        ReclassificationResult object
    """
    try:
        path_obj = Path(file_path)
        content, had_error = _read_file_content(path_obj)

        if had_error:
            return ReclassificationResult(is_error=True)

        if content is None:
            return ReclassificationResult()  # Empty, no error, no record

        # 비동기 분류 실행
        result = await classifier.classify(content)

        # 카테고리 변경 감지
        old_category = _infer_para_category(path_obj)

        # HybridClassifier returns a Dict, so we must access it with dictionary syntax
        new_category = result.get("category", "Unknown")
        is_updated = old_category.lower() != new_category.lower()

        record = ReclassificationRecord(
            record_id=str(uuid.uuid4()),
            automation_log_id=log_id,
            file_path=file_path,
            old_category=old_category,
            new_category=new_category,
            confidence_score=result.get("confidence", 0.0),
            reason=result.get("reasoning", ""),
            processed_at=datetime.now(),
        )

        return ReclassificationResult(record=record, is_updated=is_updated)

    except Exception as exc:
        if is_system_error(exc):
            raise
        meta = build_meta(
            {"action": "reclassify_file"}, file_path=Path(file_path).name, log_id=log_id
        )
        log_agent_error(
            logger, f"Error classifying file {Path(file_path).name}", exc, meta
        )
        return ReclassificationResult(is_error=True)


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
    except Exception as exc:
        if is_system_error(exc):
            raise
        meta = build_meta({"action": "init_classifier"}, log_id=log_id)
        log_agent_error(logger, "Failed to initialize classifier", exc, meta)
        return [], ClassificationStats(errors=len(files))

    records = []
    stats = ClassificationStats()

    for file_path in files:
        result = await _reclassify_file(file_path, log_id, classifier)

        if result.is_error:
            stats.errors += 1
            continue

        if result.record:
            records.append(result.record)
            stats.processed += 1
            if result.is_updated:
                stats.updated += 1

    return records, stats


def _finalize_log(
    log: AutomationLog,
    start_time: datetime,
    status: AutomationStatus,
    details: Optional[dict] = None,
) -> None:
    """AutomationLog의 완료/스킵 상태를 일관성 있게 설정하고 저장하는 헬퍼"""
    log.status = status
    if details is not None:
        log.details = details
    log.completed_at = datetime.now()
    log.duration_seconds = (log.completed_at - start_time).total_seconds()
    _save_automation_log(log)


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
            _finalize_log(
                log,
                start_time,
                AutomationStatus.SKIPPED,
                {"message": "No files found to reclassify."},
            )
            return "Skipped (No files)"

        records, stats = asyncio.run(_classify_files_async(target_files, log_id))

        log.files_processed = stats.processed
        log.files_updated = stats.updated
        log.errors_count = stats.errors

        _save_reclassification_records(records)
        _finalize_log(log, start_time, AutomationStatus.COMPLETED)

        return f"Success: {stats.processed} processed, {stats.updated} updated."

    except Exception as exc:
        if is_system_error(exc):
            raise
        meta = build_meta({"action": "execute_reclassification"}, task_name=task_name)
        log_agent_error(logger, f"[{task_name}] Failed", exc, meta)
        log.status = AutomationStatus.FAILED
        log.details = {"error": str(exc), "error_type": type(exc).__name__}
        log.completed_at = datetime.now()
        log.duration_seconds = (log.completed_at - start_time).total_seconds()
        log.errors_count += 1

        _save_automation_log(log)
        raise exc


@app.task(bind=True)
def daily_reclassify_tasks(self):
    """매일 실행: 최근 7일간 접근된 파일 재분류"""
    return _execute_reclassification(self.request.id, "daily-reclassify", days=7)


@app.task(bind=True)
def weekly_reclassify_tasks(self):
    """매주 실행: 최근 30일간 접근된 파일 심화 재분류"""
    return _execute_reclassification(self.request.id, "weekly-reclassify", days=30)

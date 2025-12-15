# backend/celery_app/tasks/maintenance.py

"""
Maintenance Tasks
자동화 시스템 유지보수 작업 (로그 정리, 백업 등)
"""

import json
import logging
import uuid
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

from backend.celery_app.celery import app
from backend.config import PathConfig
from backend.models.automation import (
    AutomationLog,
    AutomationTaskType,
    AutomationStatus,
)

logger = logging.getLogger(__name__)

# 로그 디렉토리 및 파일 설정
LOG_DIR = PathConfig.DATA_DIR / "automation_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
AUTO_LOG_FILE = LOG_DIR / "automation.jsonl"
RECLASS_LOG_FILE = LOG_DIR / "reclassification.jsonl"
ARCHIVE_LOG_FILE = LOG_DIR / "archiving.jsonl"

# 백업 디렉토리
BACKUP_DIR = PathConfig.DATA_DIR / "backups" / "automation"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _save_automation_log(log: AutomationLog):
    """AutomationLog 저장"""
    try:
        with open(AUTO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log.model_dump_json() + "\n")
    except Exception as exc:
        logger.error(
            "Failed to save maintenance log",
            exc_info=False,
            extra={"error_type": type(exc).__name__},
        )


def _create_maintenance_log(
    log_id: str,
    task_name: str,
    celery_task_id: str,
    start_time: datetime,
    status: AutomationStatus,
    details: Dict[str, Any],
    errors_count: int = 0,
) -> AutomationLog:
    """유지보수 태스크 로그 생성"""
    end_time = datetime.now()
    return AutomationLog(
        log_id=log_id,
        task_type=AutomationTaskType.MAINTENANCE,
        task_name=task_name,
        celery_task_id=celery_task_id,
        status=status,
        started_at=start_time,
        completed_at=end_time,
        duration_seconds=(end_time - start_time).total_seconds(),
        details=details,
        errors_count=errors_count,
    )


def _cleanup_jsonl_file(
    file_path: Path, days_threshold: int, date_field: str = "started_at"
) -> Dict[str, int]:
    """
    JSONL 파일에서 오래된 로그 정리

    Args:
        file_path: 로그 파일 경로
        days_threshold: 보존 기간 (일)
        date_field: 날짜 필드명

    Returns:
        {"total": 전체 로그 수, "deleted": 삭제된 로그 수, "kept": 보존된 로그 수}
    """
    if not file_path.exists():
        return {"total": 0, "deleted": 0, "kept": 0}

    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    temp_file = file_path.with_suffix(".tmp")

    total_count = 0
    kept_count = 0
    deleted_count = 0

    try:
        with open(file_path, "r", encoding="utf-8") as infile, open(
            temp_file, "w", encoding="utf-8"
        ) as outfile:

            for line in infile:
                total_count += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    log_data = json.loads(line)
                    log_date_str = log_data.get(date_field)

                    if not log_date_str:
                        # 날짜 필드 없으면 보존
                        outfile.write(line + "\n")
                        kept_count += 1
                        continue

                    # 날짜 파싱 (ISO 형식 지원)
                    try:
                        log_date = datetime.fromisoformat(
                            log_date_str.replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        # 파싱 실패 시 보존
                        outfile.write(line + "\n")
                        kept_count += 1
                        continue

                    # 보존 기간 체크
                    if log_date >= cutoff_date:
                        outfile.write(line + "\n")
                        kept_count += 1
                    else:
                        deleted_count += 1

                except json.JSONDecodeError:
                    # 잘못된 JSON은 보존 (수동 확인 필요)
                    outfile.write(line + "\n")
                    kept_count += 1

        # 원본 파일 교체
        shutil.move(str(temp_file), str(file_path))

    except Exception as exc:
        logger.error(
            f"Failed to cleanup {file_path.name}",
            exc_info=False,
            extra={"error_type": type(exc).__name__},
        )
        # 임시 파일 정리
        if temp_file.exists():
            temp_file.unlink()
        raise

    return {"total": total_count, "deleted": deleted_count, "kept": kept_count}


@app.task(bind=True)
def cleanup_old_logs(self):
    """
    [오래된 로그 정리]
    - 매일 03:00 실행
    - 30일 이상 오래된 AutomationLog 삭제
    - 90일 이상 오래된 ReclassificationRecord/ArchivingRecord 삭제
    """
    task_name = "cleanup_old_logs"
    start_time = datetime.now()
    log_id = str(uuid.uuid4())

    details: Dict[str, Any] = {}
    errors_count = 0

    try:
        # 1. AutomationLog 정리 (30일)
        auto_result = _cleanup_jsonl_file(AUTO_LOG_FILE, days_threshold=30)
        details["automation_logs"] = auto_result
        logger.info(
            f"Cleaned up automation logs: {auto_result['deleted']} deleted, {auto_result['kept']} kept"
        )

        # 2. ReclassificationRecord 정리 (90일)
        reclass_result = _cleanup_jsonl_file(
            RECLASS_LOG_FILE, days_threshold=90, date_field="processed_at"
        )
        details["reclassification_records"] = reclass_result
        logger.info(
            f"Cleaned up reclassification records: {reclass_result['deleted']} deleted, {reclass_result['kept']} kept"
        )

        # 3. ArchivingRecord 정리 (90일)
        archive_result = _cleanup_jsonl_file(
            ARCHIVE_LOG_FILE, days_threshold=90, date_field="archived_at"
        )
        details["archiving_records"] = archive_result
        logger.info(
            f"Cleaned up archiving records: {archive_result['deleted']} deleted, {archive_result['kept']} kept"
        )

        # 4. 결과 로그
        total_deleted = (
            auto_result["deleted"]
            + reclass_result["deleted"]
            + archive_result["deleted"]
        )

        log = _create_maintenance_log(
            log_id=log_id,
            task_name=task_name,
            celery_task_id=self.request.id,
            start_time=start_time,
            status=AutomationStatus.COMPLETED,
            details=details,
            errors_count=errors_count,
        )
        _save_automation_log(log)

        return f"Cleanup completed: {total_deleted} logs deleted"

    except Exception as exc:
        error_type = type(exc).__name__
        logger.error(
            f"{task_name} failed",
            exc_info=False,
            extra={"task_name": task_name, "error_type": error_type, "unhandled": True},
        )

        details["error_type"] = error_type
        log = _create_maintenance_log(
            log_id=log_id,
            task_name=task_name,
            celery_task_id=self.request.id,
            start_time=start_time,
            status=AutomationStatus.FAILED,
            details=details,
            errors_count=1,
        )
        _save_automation_log(log)
        raise


@app.task(bind=True)
def backup_automation_data(self):
    """
    [자동화 데이터 백업]
    - 주기적으로 실행 (예: 매주 일요일)
    - 모든 자동화 로그를 JSON 파일로 백업
    """
    task_name = "backup_automation_data"
    start_time = datetime.now()
    log_id = str(uuid.uuid4())

    details: Dict[str, Any] = {}
    errors_count = 0

    try:
        timestamp = start_time.strftime("%Y%m%d_%H%M%S")
        backup_files: List[str] = []

        # 백업할 파일 목록
        files_to_backup = [
            (AUTO_LOG_FILE, "automation_logs"),
            (RECLASS_LOG_FILE, "reclassification_records"),
            (ARCHIVE_LOG_FILE, "archiving_records"),
        ]

        for source_file, file_type in files_to_backup:
            if not source_file.exists():
                logger.warning(f"Backup skipped: {source_file} does not exist")
                continue

            # 백업 파일명: {type}_{timestamp}.jsonl
            backup_filename = f"{file_type}_{timestamp}.jsonl"
            backup_path = BACKUP_DIR / backup_filename

            try:
                shutil.copy2(source_file, backup_path)
                backup_files.append(str(backup_path))
                logger.info(f"Backed up {source_file.name} to {backup_filename}")

            except Exception as exc:
                logger.error(
                    f"Failed to backup {source_file.name}",
                    exc_info=False,
                    extra={"error_type": type(exc).__name__},
                )
                errors_count += 1

        details["backup_files"] = backup_files
        details["backup_count"] = len(backup_files)
        details["timestamp"] = timestamp

        status = (
            AutomationStatus.COMPLETED if errors_count == 0 else AutomationStatus.FAILED
        )

        log = _create_maintenance_log(
            log_id=log_id,
            task_name=task_name,
            celery_task_id=self.request.id,
            start_time=start_time,
            status=status,
            details=details,
            errors_count=errors_count,
        )
        _save_automation_log(log)

        return f"Backup completed: {len(backup_files)} files backed up"

    except Exception as exc:
        error_type = type(exc).__name__
        logger.error(
            f"{task_name} failed",
            exc_info=False,
            extra={"task_name": task_name, "error_type": error_type, "unhandled": True},
        )

        details["error_type"] = error_type
        log = _create_maintenance_log(
            log_id=log_id,
            task_name=task_name,
            celery_task_id=self.request.id,
            start_time=start_time,
            status=AutomationStatus.FAILED,
            details=details,
            errors_count=1,
        )
        _save_automation_log(log)
        raise

# backend/celery_app/tasks/archiving.py

import contextlib
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set

from backend.agent.error_utils import is_system_error, log_agent_error
from backend.celery_app.celery import app
from backend.config import AppConfig, PathConfig
from backend.models.automation import (
    ArchivingRecord,
    AutomationLog,
    AutomationStatus,
    AutomationTaskType,
)
from backend.services.file_access_logger import FileAccessLogger

logger = logging.getLogger(__name__)

# 로그 디렉토리 설정
LOG_DIR = PathConfig.DATA_DIR / "automation_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
AUTO_LOG_FILE = LOG_DIR / "automation.jsonl"
ARCHIVE_LOG_FILE = LOG_DIR / "archiving_records.jsonl"


@dataclass
class ArchivingResult:
    """개별 파일 아카이빙 처리 결과"""

    record: Optional[ArchivingRecord] = None
    is_error: bool = False
    is_archived: bool = False


@dataclass
class ArchivingStats:
    """아카이빙 작업 통계"""

    scanned: int = 0
    archived: int = 0
    errors: int = 0


def _save_automation_log(log: AutomationLog):
    """AutomationLog를 JSONL 파일에 저장"""
    try:
        with open(AUTO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log.model_dump_json() + "\n")
    except OSError as e:
        log_agent_error(
            logger,
            "자동화 로그 저장 실패 (I/O 오류)",
            e,
            {
                "action": "save_automation_log",
                "auto_log_file": str(AUTO_LOG_FILE),
                "log_id": getattr(log, "id", getattr(log, "log_id", None)),
            },
            level="error",
        )
    except Exception as e:
        if is_system_error(e):
            raise
        log_agent_error(
            logger,
            "자동화 로그 저장 실패 (기타)",
            e,
            {
                "action": "save_automation_log",
                "auto_log_file": str(AUTO_LOG_FILE),
                "log_id": getattr(log, "id", getattr(log, "log_id", None)),
            },
            level="error",
        )


def _save_archiving_records(records: List[ArchivingRecord]):
    """ArchivingRecord 목록을 JSONL 파일에 저장"""
    try:
        with open(ARCHIVE_LOG_FILE, "a", encoding="utf-8") as f:
            for record in records:
                f.write(record.model_dump_json() + "\n")
    except OSError as e:
        log_agent_error(
            logger,
            "아카이빙 레코드 저장 실패 (I/O 오류)",
            e,
            {
                "action": "save_archiving_records",
                "count": len(records),
                "archive_log_file": str(ARCHIVE_LOG_FILE),
            },
            level="error",
        )
    except Exception as e:
        if is_system_error(e):
            raise
        log_agent_error(
            logger,
            "아카이빙 레코드 저장 실패 (기타)",
            e,
            {
                "action": "save_archiving_records",
                "count": len(records),
                "archive_log_file": str(ARCHIVE_LOG_FILE),
            },
            level="error",
        )


def _infer_para_category(path_obj: Path) -> str:
    """파일 경로에서 현재 PARA 카테고리 추론"""
    parts = path_obj.parts
    return next(
        (
            para
            for para in ["Projects", "Areas", "Resources", "Archives", "Inbox"]
            if para in parts
        ),
        "Unknown",
    )


def _get_active_files(root_dir: Path) -> List[Path]:
    """
    아카이브 대상을 탐색하기 위해 활성 파일 목록 수집.
    - 제외 대상: Archives 폴더, 숨김 파일/폴더
    """
    active_files = []

    # PARA 폴더 중 Archives를 제외한 폴더들만 탐색하면 효율적
    target_dirs = ["Projects", "Areas", "Resources", "Inbox"]

    for category in target_dirs:
        dir_path = root_dir / category
        if not dir_path.exists():
            continue

        for root, dirs, files in os.walk(dir_path):
            # 숨김 디렉토리 제외
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for file in files:
                if file.startswith("."):
                    continue

                # 지원하는 확장자만 (설정에 따라 조정 가능, 여기선 일반적인 문서)
                if file.lower().endswith((".md", ".txt", ".pdf", ".docx")):
                    active_files.append(Path(root) / file)

    return active_files


def _is_file_inactive(path_obj: Path, recent_files_set: Set[str], days: int) -> bool:
    """
    파일 비활성 여부 판단
    1. 최근 접근 로그에 없음 (절대/상대 경로 모두 확인)
    2. 파일 시스템 수정 시간(mtime)이 N일 이상 경과
    """
    # 1. 접근 로그 확인 (다양한 경로 포맷 매칭 시도)
    candidates = set()

    # a. 절대 경로
    try:
        candidates.add(str(path_obj.resolve()))
    except Exception:
        candidates.add(str(path_obj.absolute()))

    # b. 원래 경로 문자열
    candidates.add(str(path_obj))

    # c. DATA_DIR 기준 상대 경로
    with contextlib.suppress(ValueError):
        candidates.add(str(path_obj.relative_to(PathConfig.DATA_DIR)))

    # d. BASE_DIR 기준 상대 경로
    with contextlib.suppress(ValueError):
        candidates.add(str(path_obj.relative_to(PathConfig.BASE_DIR)))

    # 교집합이 하나라도 있으면 최근 접근된 것임
    if not candidates.isdisjoint(recent_files_set):
        return False

    # 2. 파일 시스템 수정 시간 확인
    try:
        mtime = datetime.fromtimestamp(path_obj.stat().st_mtime)
        inactive_threshold = datetime.now() - timedelta(days=days)

        if mtime > inactive_threshold:
            return False  # 최근에 수정됨

    except Exception as e:
        logger.warning(f"Failed to check mtime for {path_obj}: {e}")
        return False  # 안전하게 아카이브 하지 않음

    return True


def _resolve_archive_destination(destination: Path) -> Path:
    """
    목적지 파일 이름 충돌 시 고유한 이름 생성
    - 형식: 원본명_YYYYMMDD_HHMMSS_microseconds_shortuuid.ext
    """
    if not destination.exists():
        return destination

    unique_suffix = (
        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:8]}"
    )
    new_name = f"{destination.stem}_{unique_suffix}{destination.suffix}"
    new_destination = destination.parent / new_name

    logger.info(f"Destination exists, renaming: {destination} -> {new_destination}")
    return new_destination


def _build_archive_destination(path_obj: Path) -> Path:
    """
    아카이빙 대상 파일의 목적지 경로를 결정합니다.

    DATA_DIR 기준 상대 경로를 유지하여 Archives 하위로 이동합니다.
    DATA_DIR 외부 파일은 Archives/External/ 로 이동합니다.
    """
    try:
        rel_path = path_obj.relative_to(PathConfig.DATA_DIR)
        # 예: Projects/MyProj/note.md -> Archives/Projects/MyProj/note.md
        return PathConfig.DATA_DIR / "Archives" / rel_path
    except ValueError:
        # DATA_DIR 외부에 있는 경우 (예외적)
        return PathConfig.DATA_DIR / "Archives" / "External" / path_obj.name


def _execute_archive_move(path_obj: Path, log_id: str) -> ArchivingRecord:
    """
    아카이빙 목적지 경로를 결정하고 파일을 이동한 뒤 ArchivingRecord를 반환합니다.
    충돌 시 고유한 이름으로 해결하며, 필요한 디렉토리를 자동 생성합니다.
    """
    destination = _build_archive_destination(path_obj)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = _resolve_archive_destination(destination)
    shutil.move(str(path_obj), str(destination))
    logger.info(f"Archived: {path_obj} -> {destination}")
    return ArchivingRecord(
        record_id=str(uuid.uuid4()),
        automation_log_id=log_id,
        file_path=str(path_obj),
        archive_path=str(destination),
        reason="inactive_for_30_days",
        archived_at=datetime.now(),
    )


def _archive_single_file(path_obj: Path, log_id: str) -> ArchivingResult:
    """
    단일 파일 아카이빙 실행
    - 파일을 Archives/{OriginalCategory} 폴더로 이동
    """

    try:
        record = _execute_archive_move(path_obj, log_id)
        return ArchivingResult(record=record, is_archived=True)

    except OSError as e:
        log_agent_error(
            logger,
            "파일 아카이빙 실패 (I/O 오류)",
            e,
            {
                "action": "archive_single_file",
                "source_path": str(path_obj),
                "log_id": log_id,
            },
        )
        return ArchivingResult(is_error=True)
    except Exception as e:
        if is_system_error(e):
            log_agent_error(
                logger,
                "파일 아카이빙 중 시스템 오류",
                e,
                {
                    "action": "archive_single_file",
                    "source_path": str(path_obj),
                    "log_id": log_id,
                },
            )
            raise
        log_agent_error(
            logger,
            "파일 아카이빙 실패 (기타)",
            e,
            {
                "action": "archive_single_file",
                "source_path": str(path_obj),
                "log_id": log_id,
            },
        )
        return ArchivingResult(is_error=True)


@app.task(bind=True)
def archive_inactive_files(self):
    """
    [자동 아카이브 작업]
    - 30일 이상 미접근 및 미수정 파일 탐색
    - Archives 폴더로 이동
    """
    task_name = "archive-inactive-files"
    days_threshold = AppConfig.ARCHIVE_DAYS_THRESHOLD
    start_time = datetime.now()
    log_id = str(uuid.uuid4())

    log = AutomationLog(
        log_id=log_id,
        task_type=AutomationTaskType.ARCHIVING,
        task_name=task_name,
        celery_task_id=self.request.id,
        status=AutomationStatus.RUNNING,
        started_at=start_time,
    )

    try:
        # 1. 파일 접근 로그 가져오기 (문자열 집합)
        access_logger = FileAccessLogger()
        recent_files_list = access_logger.get_recent_files(days=days_threshold)
        recent_files_set = set(recent_files_list)  # O(1) 검색을 위해 set 변환

        # 2. 모든 활성 파일 탐색
        active_files = _get_active_files(PathConfig.DATA_DIR)

        stats = ArchivingStats()
        stats.scanned = len(active_files)
        records = []

        logger.info(
            f"[{task_name}] Scanned {len(active_files)} files. Checking for inactivity..."
        )

        # 3. 비활성 파일 식별 및 아카이브
        for path_obj in active_files:
            if _is_file_inactive(path_obj, recent_files_set, days_threshold):
                result = _archive_single_file(path_obj, log_id)

                if result.is_error:
                    stats.errors += 1
                elif result.record:
                    records.append(result.record)
                    stats.archived += 1

        # 4. 결과 저장
        log.files_processed = stats.scanned
        log.files_archived = stats.archived
        log.errors_count = stats.errors

        if stats.archived == 0:
            log.details = {"message": "No inactive files found."}

        log.status = AutomationStatus.COMPLETED
        log.completed_at = datetime.now()
        log.duration_seconds = (log.completed_at - start_time).total_seconds()

        _save_archiving_records(records)
        _save_automation_log(log)

        return f"Success: {stats.scanned} scanned, {stats.archived} archived."

    except Exception as e:
        logger.exception(f"[{task_name}] Failed")
        log.status = AutomationStatus.FAILED
        log.details = {"error": str(e)}
        log.completed_at = datetime.now()
        log.duration_seconds = (log.completed_at - start_time).total_seconds()
        # Ensure errors_count is int
        log.errors_count = (0 if log.errors_count is None else log.errors_count) + 1

        _save_automation_log(log)
        raise e

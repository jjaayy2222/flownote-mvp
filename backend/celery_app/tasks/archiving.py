# backend/celery_app/tasks/archiving.py

import os
import uuid
import shutil
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set, Tuple

from backend.celery_app.celery import app
from backend.services.file_access_logger import FileAccessLogger
from backend.models.automation import (
    AutomationLog,
    AutomationTaskType,
    AutomationStatus,
    ArchivingRecord,
)
from backend.config import PathConfig, AppConfig

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
    except Exception as e:
        logger.error(f"Failed to save automation log: {e}")


def _save_archiving_records(records: List[ArchivingRecord]):
    """ArchivingRecord 목록을 JSONL 파일에 저장"""
    try:
        with open(ARCHIVE_LOG_FILE, "a", encoding="utf-8") as f:
            for record in records:
                f.write(record.model_dump_json() + "\n")
    except Exception as e:
        logger.error(f"Failed to save archiving records: {e}")


def _infer_para_category(path_obj: Path) -> str:
    """파일 경로에서 현재 PARA 카테고리 추론"""
    parts = path_obj.parts
    for para in ["Projects", "Areas", "Resources", "Archives", "Inbox"]:
        if para in parts:
            return para
    return "Unknown"


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
    try:
        candidates.add(str(path_obj.relative_to(PathConfig.DATA_DIR)))
    except ValueError:
        pass

    # d. BASE_DIR 기준 상대 경로
    try:
        candidates.add(str(path_obj.relative_to(PathConfig.BASE_DIR)))
    except ValueError:
        pass

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


def _archive_single_file(path_obj: Path, log_id: str) -> ArchivingResult:
    """
    단일 파일 아카이빙 실행
    - 파일을 Archives/{OriginalCategory} 폴더로 이동
    """

    try:
        # 목적지 경로 설정: Archives / 기존카테고리 / 파일명
        # (계층 구조 유지를 위해 relative_to 등을 사용할 수도 있으나, 단순화를 위해 1단계 하위로 이동)
        # 만약 원본이 Projects/ProjectA/note.md 라면 -> Archives/Projects/ProjectA/note.md 가 이상적

        # 여기서는 단순하게 Archives/{Category}/{FileName} 로 이동하거나
        # Archives/{Year}/{FileName} 등 전략이 필요함.
        # 요구사항: "파일 카테고리 -> Archives 변경"

        # 전략: Archives/YYYY_MM_DD_Archived/파일명 (날짜별 분류) 또는
        # Archives/{OriginalCategory}/... (구조 보존)

        # 가장 안전한 구조 보존 방식:
        # DATA_DIR로부터의 상대 경로를 유지하여 Archives 아래로 이동

        try:
            rel_path = path_obj.relative_to(PathConfig.DATA_DIR)
            # 예: Projects/MyProj/note.md

            # 목적지: Archives / (rel_path)
            # 주의: rel_path가 이미 Category로 시작하므로, Archives 밑에 또 Projects가 생김.
            # 예: Archives/Projects/MyProj/note.md -> OK.

            destination = PathConfig.DATA_DIR / "Archives" / rel_path

        except ValueError:
            # DATA_DIR 외부에 있는 경우 (예외적)
            destination = PathConfig.DATA_DIR / "Archives" / "External" / path_obj.name

        # 폴더 생성
        destination.parent.mkdir(parents=True, exist_ok=True)

        # 파일 이름 충돌 처리
        if destination.exists():
            timestamp_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"{destination.stem}_{timestamp_suffix}{destination.suffix}"
            destination = destination.parent / new_name
            logger.info(f"Destination exists, renaming to: {destination}")

        # 파일 이동
        shutil.move(str(path_obj), str(destination))
        logger.info(f"Archived: {path_obj} -> {destination}")

        record = ArchivingRecord(
            record_id=str(uuid.uuid4()),
            automation_log_id=log_id,
            file_path=str(path_obj),
            archive_path=str(destination),
            reason="inactive_for_30_days",
            archived_at=datetime.now(),
        )

        return ArchivingResult(record=record, is_archived=True)

    except Exception:
        logger.exception("Error archiving file %s", path_obj)
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
        log.errors_count = (log.errors_count or 0) + 1

        _save_automation_log(log)
        raise e

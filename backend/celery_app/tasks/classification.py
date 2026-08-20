# backend/celery_app/tasks/classification.py

import asyncio
import atexit
import hashlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from backend.agent.constants import UNKNOWN_FILE_ID
from backend.agent.error_utils import is_system_error, log_agent_error
from backend.celery_app.celery import app

# Sync & Config Imports
from backend.config.mcp_config import mcp_config
from backend.models.external_sync import (
    ConnectionConfig,
    ExternalToolConnection,
    ExternalToolType,
)
from backend.services.classification_service import ClassificationService
from backend.services.obsidian_sync import ObsidianSyncService

logger = logging.getLogger(__name__)

# Constants
INVALID_PATH_SENTINEL = "Invalid Path"
VALID_PARA_CATEGORIES = {"Projects", "Areas", "Resources", "Archive"}

# Celery 태스크 재시도 설정 상수 (하드코딩 제거)
TASK_MAX_RETRIES: int = 3
TASK_RETRY_COUNTDOWN: int = 60  # seconds

# 로컬 Obsidian 자동화 실행 시 사용되는 논리적 사용자 식별자
# PII가 아닌 시스템 역할(role)을 나타내며, 실제 사용자 데이터와 무관합니다.
LOCAL_OBSIDIAN_USER: str = "obsidian_local_agent"

# Module-level executor to avoid expensive thread creation on every call
# Used only when run_async falls back to thread offloading
# Initialized lazily to avoid resource creation if not needed
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()  # Lock for thread-safe initialization


def _build_meta(
    action: str, file_id: Optional[str], category: Optional[str] = None
) -> dict:
    meta = {
        "action": action,
        "file_id": file_id if file_id is not None else UNKNOWN_FILE_ID,
    }
    if category is not None:
        meta["category"] = category
    return meta


def _safe_path(path_str: str) -> str:
    """
    Generate a privacy-safe representation of a file path for logging.

    We deliberately avoid logging the raw filename, as it may contain PII or
    other sensitive details. Instead, we log:
      - the file extension (with leading dot if present, e.g. ".pdf", ".txt"), and
      - a truncated hash of the full path for correlation in logs.

    Returns a string like:
      'ext:.pdf (hash:deadbeef)'
    or, if no extension is present (no dot suffix):
      'ext:unknown (hash:deadbeef)'

    Returns INVALID_PATH_SENTINEL on any error or empty/None input.
    Consumers should treat this as a failure state.
    """
    if not path_str:
        return INVALID_PATH_SENTINEL

    try:
        path = Path(path_str)
        # Note: path.suffix starts with '.', e.g. '.pdf'.
        # If no suffix, we return 'unknown' explicitly.
        suffix = path.suffix or "unknown"
        path_hash = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:8]
        return f"ext:{suffix} (hash:{path_hash})"
    except Exception:
        # Fallback for invalid or unexpected path values
        return INVALID_PATH_SENTINEL


def _get_executor() -> ThreadPoolExecutor:
    """
    Get the shared ThreadPoolExecutor, initializing it safely on first use.

    This executor is process-wide and designed for reuse across Celery tasks.
    We use it to offload async work when the main thread's event loop is busy.
    """
    global _executor
    # Simplify to always acquiring lock, as this path is not hot (used only on fallback)
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1)
            # Register cleanup hook
            atexit.register(_executor.shutdown, wait=True)
    return _executor


def run_async(coro):
    """
    Run async code synchronously.

    WARNING: When a running event loop is detected, this helper executes
    the coroutine in a separate thread using asyncio.run() within a shared ThreadPoolExecutor.
    This creates a NEW event loop isolated from the current running loop.

    Ensure that the coroutine and its dependencies do not rely on objects
    bound to the original event loop (e.g. connections, locks created on the parent loop).
    Usage restricted to Celery tasks where isolation is acceptable.
    """

    # Check for running event loop
    try:
        asyncio.get_running_loop()
        has_running_loop = True
    except RuntimeError:
        has_running_loop = False

    if not has_running_loop:
        # No running loop, safe to use standard asyncio.run
        return asyncio.run(coro)

    # Active loop detected. running .result() here would block the loop -> deadlock.
    # Solution: Run standard asyncio.run in a separate thread.
    # This isolates the new async task from the existing loop.
    logger.debug("Active event loop detected. Offloading to shared executor.")
    return _get_executor().submit(asyncio.run, coro).result()


def _safe_obsidian_move(
    file_path: str,
    category: str,
    file_id: Optional[str],
    sync_service: ObsidianSyncService,
) -> Optional[str]:
    try:
        new_path = run_async(sync_service.move_file_to_para(file_path, category))
        if new_path:
            logger.info(f"Moved file to: {new_path}")
        return new_path
    except OSError as e:
        meta = _build_meta("obsidian_move", file_id, category)
        log_agent_error(
            logger,
            "Obsidian 파일 이동 실패 (분류 결과는 유지됨)",
            e,
            meta,
            level="error",
        )
        return None
    except Exception as e:
        meta = _build_meta("obsidian_move", file_id, category)
        if is_system_error(e):
            log_agent_error(logger, "Obsidian 파일 이동 중 시스템 오류", e, meta)
            raise
        log_agent_error(
            logger,
            "Obsidian 파일 이동 실패 (기타, 무시됨)",
            e,
            meta,
            level="warning",
        )
        return None


def _handle_classify_error(task_self, e: Exception, file_path: str) -> None:
    file_id = str(Path(file_path).absolute())
    meta = _build_meta("classify_file", file_id)

    if isinstance(e, OSError):
        log_agent_error(logger, "파일 I/O 오류로 분류 실패", e, meta)
        raise task_self.retry(
            exc=e, max_retries=TASK_MAX_RETRIES, countdown=TASK_RETRY_COUNTDOWN
        ) from e

    if is_system_error(e):
        log_agent_error(logger, "분류 태스크 시스템 오류", e, meta)
        raise

    log_agent_error(logger, "분류 태스크 실패", e, meta)
    raise task_self.retry(
        exc=e, max_retries=TASK_MAX_RETRIES, countdown=TASK_RETRY_COUNTDOWN
    ) from e


@app.task(bind=True)
def classify_new_file_task(self, file_path: str):
    """
    신규 파일 생성 시 호출되는 Task
    ClassificationService를 사용하여 즉시 분류 수행
    """
    safe_path = _safe_path(file_path)
    logger.info(f"Started classification for new file: {safe_path}")

    # Check if safe_path indicates an invalid path before proceeding
    if safe_path == INVALID_PATH_SENTINEL:
        logger.error("Skipping classification due to invalid file path")
        return {"status": "error", "message": "Invalid file path provided"}

    try:
        # 파일 내용 읽기
        path_obj = Path(file_path)
        if not path_obj.exists():
            logger.error(f"File not found: {safe_path}")
            return {"status": "error", "message": "File not found"}

        content = path_obj.read_text(encoding="utf-8", errors="ignore")
        if not content.strip():
            logger.warning(f"File is empty: {safe_path}")
            return {"status": "skipped", "message": "Empty file"}

        # 서비스 초기화 및 실행
        service = ClassificationService()

        # Safe async execution using helper
        # Use full absolute path as file_id to avoid collisions (Internal ID uses full path)
        file_id = str(path_obj.absolute())

        result = run_async(
            service.classify(text=content, file_id=file_id, user_id=LOCAL_OBSIDIAN_USER)
        )

        logger.info(f"Classification completed for {safe_path}: {result.category}")

        # Post-Processing: Move file to PARA folder if Obsidian Sync is enabled
        new_path = None

        if mcp_config.obsidian.enabled and result.category:
            if result.category not in VALID_PARA_CATEGORIES:
                valid_categories_display = ", ".join(sorted(VALID_PARA_CATEGORIES))
                logger.warning(
                    "Skipping move: '%s' is not a valid PARA category. Valid categories: %s",
                    result.category,
                    valid_categories_display,
                )
            else:
                # Construct Connection (Stateless connection for this task)
                conn = ExternalToolConnection(
                    tool_type=ExternalToolType.OBSIDIAN,
                    config=ConnectionConfig(
                        base_path=mcp_config.obsidian.vault_path, enabled=True
                    ),
                )
                sync_service = ObsidianSyncService(conn)
                new_path = _safe_obsidian_move(
                    file_path, result.category, file_id, sync_service
                )

        return {
            "status": "success",
            "category": result.category,
            "confidence": result.confidence,
            "new_path": new_path,
        }

    except Exception as e:
        _handle_classify_error(self, e, file_path)


@app.task(bind=True)
def update_embedding_task(self, file_path: str):
    """
    파일 수정 시 호출되는 Task (임베딩 업데이트)
    """
    logger.info(f"Updating embedding for: {_safe_path(file_path)}")
    return {"status": "pending_implementation", "file_path": file_path}

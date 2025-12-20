# backend/celery_app/tasks/classification.py

import asyncio
import logging
import atexit
import threading
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from backend.celery_app.celery import app
from backend.services.classification_service import ClassificationService

logger = logging.getLogger(__name__)

# Module-level executor to avoid expensive thread creation on every call
# Used only when run_async falls back to thread offloading
# Initialized lazily to avoid resource creation if not needed
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()  # Lock for thread-safe initialization


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

    Returns 'Invalid Path' on any error or empty/None input.
    Consumers should treat 'Invalid Path' as a failure state.
    """
    if not path_str:
        return "Invalid Path"

    try:
        path = Path(path_str)
        # Note: path.suffix starts with '.', e.g. '.pdf'.
        # If no suffix, we return 'unknown' explicitly.
        suffix = path.suffix if path.suffix else "unknown"
        path_hash = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:8]
        return f"ext:{suffix} (hash:{path_hash})"
    except Exception:
        # Fallback for invalid or unexpected path values
        return "Invalid Path"


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

    if has_running_loop:
        # Active loop detected. running .result() here would block the loop -> deadlock.
        # Solution: Run standard asyncio.run in a separate thread.
        # This isolates the new async task from the existing loop.
        logger.debug("Active event loop detected. Offloading to shared executor.")
        return _get_executor().submit(asyncio.run, coro).result()
    else:
        # No running loop, safe to use standard asyncio.run
        return asyncio.run(coro)


@app.task(bind=True)
def classify_new_file_task(self, file_path: str):
    """
    신규 파일 생성 시 호출되는 Task
    ClassificationService를 사용하여 즉시 분류 수행
    """
    safe_path = _safe_path(file_path)
    logger.info(f"🚀 Started classification for new file: {safe_path}")

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
            service.classify(
                text=content, file_id=file_id, user_id="obsidian_user"  # 로컬 유저 가정
            )
        )

        logger.info(f"✅ Classification completed for {safe_path}: {result.category}")
        return {
            "status": "success",
            "category": result.category,
            "confidence": result.confidence,
        }

    except Exception as e:
        logger.exception(f"Error classifying file {safe_path}")
        return {"status": "error", "message": "Internal error during classification"}


@app.task(bind=True)
def update_embedding_task(self, file_path: str):
    """
    파일 수정 시 호출되는 Task (임베딩 업데이트)
    """
    logger.info(f"🔄 Updating embedding for: {_safe_path(file_path)}")
    return {"status": "pending_implementation", "file_path": file_path}

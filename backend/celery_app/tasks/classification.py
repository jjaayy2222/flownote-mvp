# backend/celery_app/tasks/classification.py

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

from backend.celery_app.celery import app
from backend.services.classification_service import ClassificationService

logger = logging.getLogger(__name__)


def run_async(coro):
    """
    Run async code synchronously.

    Uses asyncio.run in the normal case; if already inside a running
    event loop, falls back to thread-safe submission.
    """
    try:
        # If this does not raise, we're already inside a running event loop
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop in this thread: use asyncio.run for simplicity
        return asyncio.run(coro)
    else:
        # Running loop detected: submit coroutine in a thread-safe way
        # Note: run_coroutine_threadsafe returns a concurrent.futures.Future
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()


@app.task(bind=True)
def classify_new_file_task(self, file_path: str):
    """
    신규 파일 생성 시 호출되는 Task
    ClassificationService를 사용하여 즉시 분류 수행
    """
    logger.info(f"🚀 Started classification for new file: {file_path}")

    try:
        # 파일 내용 읽기
        path_obj = Path(file_path)
        if not path_obj.exists():
            logger.error(f"File not found: {file_path}")
            return {"status": "error", "message": "File not found"}

        content = path_obj.read_text(encoding="utf-8", errors="ignore")
        if not content.strip():
            logger.warning(f"File is empty: {file_path}")
            return {"status": "skipped", "message": "Empty file"}

        # 서비스 초기화 및 실행
        service = ClassificationService()

        # Safe async execution using helper
        # Use full absolute path as file_id to avoid collisions
        file_id = str(path_obj.absolute())

        result = run_async(
            service.classify(
                text=content, file_id=file_id, user_id="obsidian_user"  # 로컬 유저 가정
            )
        )

        logger.info(f"✅ Classification completed for {file_path}: {result.category}")
        return {
            "status": "success",
            "category": result.category,
            "confidence": result.confidence,
        }

    except Exception as e:
        logger.exception(f"Error classifying file {file_path}")
        return {"status": "error", "message": str(e)}


@app.task(bind=True)
def update_embedding_task(self, file_path: str):
    """
    파일 수정 시 호출되는 Task (임베딩 업데이트)
    """
    logger.info(f"🔄 Updating embedding for: {file_path}")
    return {"status": "pending_implementation", "file_path": file_path}

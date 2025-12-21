# backend/services/obsidian_watcher.py

import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend.config.mcp_config import mcp_config
from backend.celery_app.tasks.classification import (
    classify_new_file_task,
    update_embedding_task,
)
from backend.services.ignore_manager import ignore_manager

logger = logging.getLogger(__name__)


class ObsidianFileEventHandler(FileSystemEventHandler):
    """
    Obsidian Vault 파일 시스템 이벤트 핸들러
    """

    def __init__(self):
        super().__init__()

    def _is_valid_file(self, path_str: str) -> bool:
        """Markdown 파일이고 숨김 파일이 아닌지 확인 (숨김 디렉터리도 제외)"""
        path = Path(path_str)
        return (
            path.suffix == ".md"
            # 파일 자체가 숨김 파일이 아니고
            and not path.name.startswith(".")
            # 경로 중 어떤 부분도 숨김 디렉터리가 아니어야 함 (예: .obsidian, .git 등)
            and all(not part.startswith(".") for part in path.parts)
        )

    def on_created(self, event):
        if event.is_directory:
            return

        if ignore_manager.is_ignored(event.src_path):
            logger.info(
                f"🙈 Ignoring created event (Loop Prevention): {event.src_path}"
            )
            return

        if self._is_valid_file(event.src_path):
            logger.info(f"✨ New file detected: {event.src_path}")
            # Trigger Celery Task (Async)
            classify_new_file_task.delay(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return

        if ignore_manager.is_ignored(event.src_path):
            logger.info(
                f"🙈 Ignoring modified event (Loop Prevention): {event.src_path}"
            )
            return

        if self._is_valid_file(event.src_path):
            logger.info(f"📝 File modified: {event.src_path}")
            # Trigger Celery Task (Async)
            update_embedding_task.delay(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return

        # Check destination path for ignore
        if ignore_manager.is_ignored(event.dest_path):
            logger.info(f"🙈 Ignoring moved event (Loop Prevention): {event.dest_path}")
            return

        if self._is_valid_file(event.dest_path):
            logger.info(f"📦 File moved: {event.src_path} -> {event.dest_path}")
            # Treat move/rename as update
            update_embedding_task.delay(event.dest_path)


class ObsidianWatcherService:
    """
    Obsidian Directory Watcher Service
    """

    def __init__(self):
        self.config = mcp_config.obsidian
        self.observer: Optional[Observer] = None
        self.handler = ObsidianFileEventHandler()

    def start(self):
        """Watcher 시작"""
        if not self.config.enabled:
            logger.info("🚫 Obsidian sync disabled in config.")
            return

        if not self.config.is_valid:
            logger.error(f"❌ Invalid Obsidian Vault path: {self.config.vault_path}")
            return

        path = self.config.vault_path
        self.observer = Observer()
        self.observer.schedule(self.handler, path, recursive=True)
        self.observer.start()
        logger.info(f"👀 Started watching Obsidian Vault at: {path}")

    def stop(self):
        """Watcher 중지"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("🛑 Stopped watching Obsidian Vault")


# Global Service Instance
obsidian_watcher = ObsidianWatcherService()

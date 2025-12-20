# backend/services/obsidian_watcher.py

import time
import logging
from pathlib import Path
from typing import Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend.config.mcp_config import mcp_config
from backend.celery_app.tasks.classification import (
    classify_new_file_task,
    update_embedding_task,
)

logger = logging.getLogger(__name__)


class ObsidianFileEventHandler(FileSystemEventHandler):
    """
    Obsidian Vault 파일 시스템 이벤트 핸들러
    """

    def __init__(self):
        super().__init__()

    def _is_valid_file(self, path_str: str) -> bool:
        """Markdown 파일이고 숨김 파일이 아닌지 확인"""
        path = Path(path_str)
        return (
            path.suffix == ".md"
            and not path.name.startswith(".")
            and not ".obsidian" in path.parts
        )

    def on_created(self, event):
        if not event.is_directory and self._is_valid_file(event.src_path):
            logger.info(f"✨ New file detected: {event.src_path}")
            # Trigger Celery Task (Async)
            classify_new_file_task.delay(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._is_valid_file(event.src_path):
            logger.info(f"📝 File modified: {event.src_path}")
            # Trigger Celery Task (Async)
            update_embedding_task.delay(event.src_path)

    def on_moved(self, event):
        if not event.is_directory and self._is_valid_file(event.dest_path):
            logger.info(f"📦 File moved: {event.src_path} -> {event.dest_path}")
            # Treat move/rename as new file for classification check?
            # Or update embedding registry.
            # For now, trigger embedding update on destination
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

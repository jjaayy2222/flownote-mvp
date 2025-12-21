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

    def _should_process(self, event, path: str, event_type: str) -> bool:
        """
        이벤트 처리 여부 결정 헬퍼
        공통 체크: 디렉터리 여부, Ignore 목록, 파일 유효성
        """
        if event.is_directory:
            return False

        if ignore_manager.is_ignored(path):
            logger.info(f"🙈 Ignoring {event_type} event (Loop Prevention): {path}")
            return False

        return self._is_valid_file(path)

    def on_created(self, event):
        if not self._should_process(event, event.src_path, "created"):
            return

        logger.info(f"✨ New file detected: {event.src_path}")
        # Trigger Celery Task (Async)
        classify_new_file_task.delay(event.src_path)

    def on_modified(self, event):
        if not self._should_process(event, event.src_path, "modified"):
            return

        logger.info(f"📝 File modified: {event.src_path}")
        # Trigger Celery Task (Async)
        update_embedding_task.delay(event.src_path)

    def on_moved(self, event):
        # We process the destination path for updates
        if not self._should_process(event, event.dest_path, "moved"):
            return

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

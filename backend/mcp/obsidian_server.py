# backend/mcp/obsidian_server.py

"""
Obsidian Sync Server
Watchdog을 사용하여 로컬 Obsidian Vault의 변경 사항을 감지하고 동기화합니다.
"""

import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Callable, Any

import aiofiles
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend.config.mcp_config import ObsidianConfig
from backend.services.sync_service import SyncServiceBase
from backend.models.external_sync import ExternalToolConnection, ExternalToolType
from backend.models.conflict import SyncConflict

logger = logging.getLogger(__name__)


class ObsidianFileWatcher(FileSystemEventHandler):
    """
    Obsidian Vault 파일 변경 감지 핸들러
    """

    def __init__(self, callback: Callable[[str, str], None]):
        # Callback signature: (file_path, event_type)
        self.callback = callback

    def _is_target(self, event):
        return not event.is_directory and event.src_path.endswith(".md")

    def on_modified(self, event):
        if self._is_target(event):
            self.callback(event.src_path, "modified")

    def on_created(self, event):
        if self._is_target(event):
            self.callback(event.src_path, "created")

    def on_moved(self, event):
        if self._is_target(event):
            # dest_path가 md인지도 확인 필요
            if event.dest_path.endswith(".md"):
                self.callback(
                    event.dest_path, "moved"
                )  # Source path handling needed? MVP: Treat as create at dest

    def on_deleted(self, event):
        if self._is_target(event):
            self.callback(event.src_path, "deleted")


class ObsidianSyncService(SyncServiceBase):
    """
    Obsidian 동기화 서비스 구현체
    """

    def __init__(self, config: ObsidianConfig):
        # 연결 정보 생성
        connection = ExternalToolConnection(
            tool_type=ExternalToolType.OBSIDIAN,
            config={"vault_path": config.vault_path, "enabled": config.enabled},
        )
        super().__init__(connection)

        self.vault_path = Path(config.vault_path)
        self.observer: Optional[Observer] = None
        self.watcher: Optional[ObsidianFileWatcher] = None
        self.is_watching = False

        # Async Event Loop 참조 (Thread-safe interaction 용)
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    async def connect(self) -> bool:
        """Vault 경로 확인 연결 테스트"""
        if not self.loop:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("⚠️ No running event loop found during connect().")

        if not self.vault_path.exists():
            logger.error(f"❌ Obsidian Vault Path not found: {self.vault_path}")
            return False
        if not self.vault_path.is_dir():
            logger.error(f"❌ Path is not a directory: {self.vault_path}")
            return False

        logger.info(f"✅ Connected to Obsidian Vault at {self.vault_path}")
        return True

    def start_watching(self):
        """파일 감시 시작 (Background Thread)"""
        # 경로가 디렉토리인지 추가 검증 (Bug fix)
        if (
            self.is_watching
            or not self.vault_path.exists()
            or not self.vault_path.is_dir()
        ):
            logger.warning(
                f"❌ Cannot start watching: Invalid vault path {self.vault_path}"
            )
            return

        # Watchdog 콜백 연결
        self.watcher = ObsidianFileWatcher(self._on_file_change)
        self.observer = Observer()
        self.observer.schedule(self.watcher, str(self.vault_path), recursive=True)
        self.observer.start()
        self.is_watching = True
        logger.info(f"👀 Started watching Obsidian Vault: {self.vault_path}")

    def stop_watching(self):
        """파일 감시 중단"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.is_watching = False
            logger.info("🛑 Stopped watching Obsidian Vault")

    def _on_file_change(self, file_path: str, event_type: str):
        """
        Watchdog 콜백 (별도 스레드에서 실행됨)
        """
        logger.info(f"🔄 File {event_type}: {file_path}")
        # TODO: Schedule async sync task via run_coroutine_threadsafe

    async def sync_all(self) -> List[SyncConflict]:
        """
        전체 파일 스캔 및 동기화 (MVP: 단순 스캔)
        """
        if not self.vault_path.exists():
            return []

        conflicts = []
        # 재귀적으로 md 파일 탐색 (Generator expression directly in loop)
        for file_path in self.vault_path.rglob("*.md"):
            # TODO: Match with internal DB hash
            pass

        return conflicts

    async def pull_file(self, external_id: str) -> Optional[str]:
        """
        외부 파일 읽기 (external_id = absolute path)
        """
        path = Path(external_id)
        if not path.exists():
            return None

        try:
            async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
                return await f.read()
        except Exception as e:
            logger.error(f"Failed to pull file {external_id}: {e}")
            return None

    async def push_file(self, internal_id: str, content: str) -> bool:
        """
        내부 파일을 Vault로 쓰기
        """
        filename = internal_id if internal_id.endswith(".md") else f"{internal_id}.md"
        target_path = self.vault_path / filename

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(target_path, mode="w", encoding="utf-8") as f:
                await f.write(content)
            logger.info(f"Saved file to Obsidian: {target_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to push file {target_path}: {e}")
            return False

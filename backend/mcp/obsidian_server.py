# backend/mcp/obsidian_server.py

"""
Obsidian Sync Server
Watchdog을 사용하여 로컬 Obsidian Vault의 변경 사항을 감지하고 동기화합니다.
"""

import asyncio
import logging
from pathlib import Path
from typing import Callable, List, Optional

import aiofiles  # type: ignore[import-untyped]
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from backend.agent.error_utils import (  # type: ignore[import]
    build_meta,
    get_safe_file_id,
    log_agent_error,
)
from backend.config.mcp_config import ObsidianConfig
from backend.mcp.sync_map_manager import get_sync_map_manager
from backend.models.conflict import SyncConflict
from backend.models.external_sync import ExternalToolConnection, ExternalToolType
from backend.services.sync_service import SyncServiceBase

logger = logging.getLogger(__name__)


class ObsidianFileWatcher(FileSystemEventHandler):
    """
    Obsidian Vault 파일 변경 감지 핸들러
    """

    def __init__(self, callback: Callable[[str, str], None]):
        # Callback signature: (file_path, event_type)
        self.callback = callback

    def _is_md_file(self, path: str) -> bool:
        """Check if path is a markdown file"""
        return path.endswith(".md")

    def on_modified(self, event):
        if not event.is_directory and self._is_md_file(event.src_path):
            self.callback(event.src_path, "modified")

    def on_created(self, event):
        if not event.is_directory and self._is_md_file(event.src_path):
            self.callback(event.src_path, "created")

    def on_moved(self, event):
        # Handle both src and dest being md, or rename to md
        if not event.is_directory and self._is_md_file(event.dest_path):
            self.callback(event.dest_path, "moved")

    def on_deleted(self, event):
        if not event.is_directory and self._is_md_file(event.src_path):
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
        self.observer: Optional[BaseObserver] = None
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
            logger.error("❌ Obsidian Vault Path not found: %s", self.vault_path.name)
            return False
        if not self.vault_path.is_dir():
            logger.error("❌ Path is not a directory: %s", self.vault_path.name)
            return False

        logger.info("✅ Connected to Obsidian Vault at %s", self.vault_path.name)
        return True

    def start_watching(self):
        """파일 감시 시작 (Background Thread)"""
        if (
            self.is_watching
            or not self.vault_path.exists()
            or not self.vault_path.is_dir()
        ):
            logger.warning(
                f"❌ Cannot start watching: Invalid vault path {self.vault_path.name}"
            )
            return

        # Watchdog 콜백 연결
        self.watcher = ObsidianFileWatcher(self._on_file_change)
        self.observer = Observer()
        self.observer.schedule(self.watcher, str(self.vault_path), recursive=True)
        self.observer.start()
        self.is_watching = True
        logger.info("👀 Started watching Obsidian Vault: %s", self.vault_path.name)

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
        Event Loop에 비동기 작업 스케줄링
        """
        logger.info("🔄 File %s: %s", event_type, Path(file_path).name)

        # Schedule async sync task if loop is available
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._process_file_change(file_path, event_type), self.loop
            )
        else:
            logger.warning("⚠️ Event loop not available, cannot schedule sync task")

    async def _process_file_change(self, file_path: str, event_type: str):
        """변경된 Vault 파일을 매핑된 로컬 파일과 비교한다."""
        path = self._get_vault_markdown_path(file_path)
        if path is None or event_type == "deleted":
            return

        conflict = await self._sync_mapped_file(path)
        if conflict:
            logger.info(
                "Obsidian conflict detected (file_id=%s)",
                get_safe_file_id(conflict.file_id),
            )

    def _get_vault_markdown_path(self, file_path: str) -> Optional[Path]:
        """Vault 내부의 기존 Markdown 파일만 반환해 경로 이탈을 차단한다."""
        try:
            vault_root = self.vault_path.resolve()
            path = Path(file_path).resolve()
            path.relative_to(vault_root)
            if path.suffix.lower() != ".md" or not path.is_file():
                return None
            return path
        except (OSError, ValueError):
            return None

    async def _sync_mapped_file(self, external_path: Path) -> Optional[SyncConflict]:
        """매핑된 파일을 3-way 비교하고 단일 측 변경을 반대편에 반영한다."""
        manager = get_sync_map_manager()
        mapping = manager.get_mapping_by_external_path(str(external_path))
        if mapping is None or not mapping.last_synced_hash:
            return None

        local_path = Path(mapping.internal_file_id)
        try:
            async with aiofiles.open(external_path, mode="r", encoding="utf-8") as file:
                remote_content = await file.read()
            local_content = await asyncio.to_thread(
                local_path.read_text, encoding="utf-8"
            )
        except (OSError, UnicodeDecodeError) as exc:
            meta = build_meta(
                {
                    "action": "compare_mapped_file",
                    "file_id": get_safe_file_id(mapping.internal_file_id),
                }
            )
            log_agent_error(
                logger, "Failed to read files for sync comparison", exc, meta
            )
            return None

        local_hash = self.calculate_file_hash(local_content)
        remote_hash = self.calculate_file_hash(remote_content)
        last_synced_hash = mapping.last_synced_hash
        local_changed = local_hash != last_synced_hash
        remote_changed = remote_hash != last_synced_hash

        if not local_changed and not remote_changed:
            return None
        if local_changed and remote_changed and local_hash != remote_hash:
            return self.detect_conflict_3way(
                file_id=mapping.internal_file_id,
                external_path=str(external_path),
                local_hash=local_hash,
                remote_hash=remote_hash,
                last_synced_hash=last_synced_hash,
            )

        if local_hash != remote_hash:
            if local_changed:
                synced = await self.push_file(str(external_path), local_content)
            else:
                try:
                    async with aiofiles.open(
                        local_path, mode="w", encoding="utf-8"
                    ) as file:
                        await file.write(remote_content)
                    synced = True
                except (OSError, UnicodeEncodeError) as exc:
                    meta = build_meta(
                        {
                            "action": "pull_file_to_local",
                            "file_id": get_safe_file_id(mapping.internal_file_id),
                        }
                    )
                    log_agent_error(
                        logger, "Failed to apply remote file change", exc, meta
                    )
                    synced = False
            if not synced:
                return None

        await asyncio.to_thread(
            manager.update_mapping,
            internal_id=mapping.internal_file_id,
            external_path=str(external_path),
            tool_type=self.tool_type,
            current_hash=remote_hash,
        )
        return None

    async def sync_all(self) -> List[SyncConflict]:
        """Vault의 매핑된 Markdown 파일을 스캔해 양쪽 변경 충돌을 수집한다."""
        if not self.vault_path.exists() or not self.vault_path.is_dir():
            return []

        try:
            files = await asyncio.to_thread(lambda: list(self.vault_path.rglob("*.md")))
        except OSError as exc:
            meta = build_meta({"action": "scan_vault"})
            log_agent_error(logger, "Failed to scan Obsidian Vault", exc, meta)
            return []

        conflicts: List[SyncConflict] = []
        for candidate in files:
            path = self._get_vault_markdown_path(str(candidate))
            if path is None:
                continue
            conflict = await self._sync_mapped_file(path)
            if conflict:
                conflicts.append(conflict)

        return conflicts

    async def pull_file(self, external_id: str) -> Optional[str]:
        """외부 파일 읽기 (external_id = absolute path)"""
        path = Path(external_id)
        if not path.exists():
            return None

        try:
            async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
                return await f.read()
        except (OSError, UnicodeDecodeError) as e:
            meta = build_meta({"action": "pull_file", "filename": path.name})
            log_agent_error(logger, "Failed to pull file", e, meta)
            return None

    async def push_file(self, internal_id: str, content: str) -> bool:
        """내부 파일을 Vault로 쓰기"""
        filename = internal_id if internal_id.endswith(".md") else f"{internal_id}.md"
        target_path = self.vault_path / filename

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(target_path, mode="w", encoding="utf-8") as f:
                await f.write(content)
            logger.info("Saved file to Obsidian: %s", target_path.name)
            return True
        except (OSError, UnicodeEncodeError) as e:
            meta = build_meta({"action": "push_file", "filename": target_path.name})
            log_agent_error(logger, "Failed to push file", e, meta)
            return False

# backend/services/obsidian_sync.py

import os
import shutil
import logging
import asyncio
from pathlib import Path
from typing import Optional, List

from backend.services.sync_service import SyncServiceBase
from backend.services.ignore_manager import ignore_manager
from backend.models.external_sync import ExternalToolConnection, SyncStatus
from backend.models.conflict import SyncConflict

logger = logging.getLogger(__name__)


class ObsidianSyncService(SyncServiceBase):
    """
    Obsidian Vault와의 동기화를 담당하는 서비스 구현체
    - 파일 이동 (PARA 분류)
    - 내용 읽기/쓰기
    - Loop Prevention (IgnoreManager 연동)
    """

    def __init__(self, connection: ExternalToolConnection):
        super().__init__(connection)
        self.vault_path = Path(connection.config.base_path)

    async def connect(self) -> bool:
        """Vault 경로 유효성 확인"""
        if not self.vault_path.exists():
            logger.error(f"Obsidian Vault path not found: {self.vault_path}")
            return False
        return True

    async def sync_all(self) -> List[SyncConflict]:
        """
        전체 동기화 (현재는 Placeholder)
        추후 전체 스캔 및 DB 메타데이터 비교 로직 구현 필요
        """
        logger.info("Executing full sync for Obsidian...")
        return []

    async def pull_file(self, external_id: str) -> Optional[str]:
        """파일 내용 읽기 (external_id = absolute path string)"""
        try:
            path = Path(external_id)
            if not path.exists():
                return None
            return await asyncio.to_thread(path.read_text, encoding="utf-8")
        except Exception as e:
            logger.error(f"Error reading file {external_id}: {e}")
            return None

    async def push_file(self, internal_id: str, content: str) -> bool:
        """
        파일 내용 쓰기 (internal_id = absolute path string)
        NOTE: Watchdog Loop를 방지하기 위해 ignore_manager를 사용해야 함
        """
        try:
            path = Path(internal_id)

            # Loop Prevention: 쓰기 직전에 무시 목록에 추가
            ignore_manager.add(str(path))

            await asyncio.to_thread(path.write_text, content, encoding="utf-8")
            logger.info(f"Successfully wrote to {path}")
            return True
        except Exception as e:
            logger.error(f"Error writing file {internal_id}: {e}")
            return False

    async def move_file_to_para(self, file_path: str, category: str) -> Optional[str]:
        """
        파일을 PARA 카테고리 폴더로 이동

        Args:
            file_path: 이동할 원본 파일의 절대 경로
            category: 대상 카테고리 (Projects, Areas, Resources, Archive)

        Returns:
            이동된 파일의 새로운 절대 경로 (실패 시 None)
        """
        try:
            src_path = Path(file_path)
            if not src_path.exists():
                logger.error(f"Source file not found: {src_path}")
                return None

            # 카테고리 폴더 매핑 (단순화: 1.Projects 등 번호가 있을 수도 있으나 일단 이름 그대로 매칭 시도)
            # Vault Root 바로 아래에 해당 카테고리 폴더가 있다고 가정
            target_dir = self.vault_path / category

            # 폴더가 없으면 생성
            if not target_dir.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created category directory: {target_dir}")

            dest_path = target_dir / src_path.name

            # 이미 같은 위치에 있다면 스킵
            if src_path.resolve() == dest_path.resolve():
                logger.info(f"File already in correct category: {dest_path}")
                return str(dest_path)

            # 이름 충돌 방지 (덮어쓰기 방지)
            if dest_path.exists():
                timestamp = int(os.path.getmtime(str(src_path)))
                stem = src_path.stem
                suffix = src_path.suffix
                new_name = f"{stem}_{timestamp}{suffix}"
                dest_path = target_dir / new_name
                logger.warning(f"File name conflict. Renaming to: {new_name}")

            # Loop Prevention: 이동 대상 경로 무시
            # shutil.move는 copy+delete가 될 수도, rename이 될 수도 있음.
            # 안전하게 src(delete 이벤트)와 dest(create/move 이벤트) 모두 잠시 무시
            ignore_manager.add(str(src_path))
            ignore_manager.add(str(dest_path))

            await asyncio.to_thread(shutil.move, str(src_path), str(dest_path))
            logger.info(f"Moved file: {src_path.name} -> {category}/{dest_path.name}")

            return str(dest_path)

        except Exception as e:
            logger.exception(f"Failed to move file {file_path} to {category}")
            return None

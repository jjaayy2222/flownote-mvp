# backend/mcp/sync_map_manager.py

"""
Sync Map Manager (Option 2) for Scalable MCP Integration
외부 파일과 내부 파일 간의 매핑 정보를 독립적으로 관리합니다.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime

from backend.models.external_sync import ExternalFileMapping, ExternalToolType
from backend.config import PathConfig

logger = logging.getLogger(__name__)


class SyncMapManager:
    """
    동기화 매핑 데이터 관리자
    - JSON 파일 기반 영속성 관리
    - Thread-safe (Locking)
    - O(1) Path Lookup Indexing
    """

    def __init__(self, storage_dir: str = "mcp", filename: str = "file_mappings.json"):
        self.storage_path = PathConfig.DATA_DIR / storage_dir / filename

        # In-memory storage
        self._mappings: Dict[str, ExternalFileMapping] = {}
        self._path_index: Dict[str, str] = {}

        # Thread Lock
        self._lock = threading.Lock()

        # 저장소 디렉토리 생성
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # 데이터 로드
        self._load_mappings()

    def _load_mappings(self):
        """JSON 파일에서 매핑 데이터 로드"""
        if not self.storage_path.exists():
            logger.info("ℹ️ No mapping file found, initializing empty.")
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                count = 0
                for item in data:
                    try:
                        mapping = ExternalFileMapping(**item)
                        self._mappings[mapping.internal_file_id] = mapping
                        self._path_index[mapping.external_path] = (
                            mapping.internal_file_id
                        )
                        count += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to parse mapping item: {e}")

                logger.info(
                    f"✅ Loaded {count} file mappings from {self.storage_path.name}"
                )
        except Exception as e:
            logger.error(f"❌ Failed to load mappings: {e}")

    def _save_mappings(self, snapshot: List[ExternalFileMapping]):
        """메모리 상의 매핑 데이터를 JSON 파일로 저장 (Lock 밖에서 호출)"""
        try:
            data = [m.model_dump(mode="json") for m in snapshot]

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(data)} mappings to disk.")
        except Exception as e:
            logger.error(f"❌ Failed to save mappings: {e}")

    def get_mapping_by_internal_id(
        self, internal_id: str
    ) -> Optional[ExternalFileMapping]:
        """내부 파일 ID로 매핑 조회 (Thread-safe)"""
        with self._lock:
            return self._mappings.get(internal_id)

    def get_mapping_by_external_path(
        self, external_path: str
    ) -> Optional[ExternalFileMapping]:
        """외부 경로로 매핑 조회 (Thread-safe, O(1))"""
        with self._lock:
            if internal_id := self._path_index.get(external_path):
                return self._mappings.get(internal_id)
            return None

    def update_mapping(
        self,
        internal_id: str,
        external_path: str,
        tool_type: ExternalToolType,
        current_hash: Optional[str] = None,
    ) -> ExternalFileMapping:
        """매핑 정보 생성 또는 갱신 (Thread-safe)"""
        with self._lock:
            mapping = self._mappings.get(internal_id)

            if mapping:
                mapping = self._update_existing_mapping(
                    mapping, external_path, tool_type, current_hash
                )
            else:
                mapping = self._create_new_mapping(
                    internal_id, external_path, tool_type, current_hash
                )

            # Update Index
            self._path_index[external_path] = internal_id

            # Create Snapshot
            snapshot = list(self._mappings.values())

        # Save outside lock
        self._save_mappings(snapshot)
        return mapping

    def _update_existing_mapping(
        self,
        mapping: ExternalFileMapping,
        external_path: str,
        tool_type: ExternalToolType,
        current_hash: Optional[str],
    ) -> ExternalFileMapping:
        """기존 매핑 업데이트 (Lock 안에서 호출)"""
        old_path = mapping.external_path

        # Remove old path from index
        if old_path in self._path_index:
            del self._path_index[old_path]

        # Update fields
        mapping.external_path = external_path
        mapping.tool_type = tool_type
        mapping.last_synced_at = datetime.now()

        if current_hash:
            mapping.last_synced_hash = current_hash

        logger.info(f"Updated mapping for {mapping.internal_file_id}")
        return mapping

    def _create_new_mapping(
        self,
        internal_id: str,
        external_path: str,
        tool_type: ExternalToolType,
        current_hash: Optional[str],
    ) -> ExternalFileMapping:
        """새 매핑 생성 (Lock 안에서 호출)"""
        mapping = ExternalFileMapping(
            internal_file_id=internal_id,
            external_path=external_path,
            tool_type=tool_type,
            last_synced_hash=current_hash,
            last_synced_at=datetime.now(),
        )
        self._mappings[internal_id] = mapping
        logger.info(f"Created new mapping for {internal_id} <-> {external_path}")
        return mapping

    def remove_mapping(self, internal_id: str) -> bool:
        """매핑 삭제 (Thread-safe)"""
        snapshot = None

        with self._lock:
            if internal_id in self._mappings:
                mapping = self._mappings[internal_id]

                # Remove from index
                if mapping.external_path in self._path_index:
                    del self._path_index[mapping.external_path]

                # Remove from mappings
                del self._mappings[internal_id]

                # Create snapshot
                snapshot = list(self._mappings.values())
                logger.info(f"Removed mapping for {internal_id}")

        if snapshot is not None:
            self._save_mappings(snapshot)
            return True

        return False

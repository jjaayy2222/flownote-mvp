# backend/services/sync_service.py

"""
Sync Service Abstraction
외부 도구 동기화 서비스의 기본 인터페이스 정의
"""

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from backend.agent.error_utils import build_meta, get_safe_file_id, log_agent_error
from backend.config import PathConfig
from backend.models.conflict import SyncConflict, SyncConflictType
from backend.models.external_sync import ExternalToolConnection

logger = logging.getLogger(__name__)

# 충돌 레코드 JSONL 저장 경로 (PathConfig 기반)
_SYNC_LOG_DIR = PathConfig.DATA_DIR / "sync_logs"
_CONFLICT_RECORD_FILE = _SYNC_LOG_DIR / "detected_conflicts.jsonl"


class SyncServiceBase(ABC):
    """
    모든 외부 동기화 서비스(Obsidian, Notion 등)의 Base Class

    공통 기능:
    - 파일 해시 계산
    - 기본 충돌 감지
    - 인터페이스 정의 (pull, push, sync)
    """

    def __init__(self, connection: ExternalToolConnection):
        self.connection = connection
        self.tool_type = connection.tool_type

    @abstractmethod
    async def connect(self) -> bool:
        """도구 연결 확인"""

    @abstractmethod
    async def sync_all(self) -> List[SyncConflict]:
        """전체 동기화 수행"""

    @abstractmethod
    async def pull_file(self, external_id: str) -> Optional[str]:
        """외부 파일 가져오기 (내용 반환)"""

    @abstractmethod
    async def push_file(self, internal_id: str, content: str) -> bool:
        """내부 파일을 외부로 내보내기"""

    def calculate_file_hash(self, content: str) -> str:
        """
        파일 내용의 SHA-256 해시 계산
        변경 감지 및 충돌 비교용
        """
        if content is None:
            return ""
        # 정규화: 줄바꿈 문자 통일 (CRLF -> LF)
        # 선행/후행 공백 및 마지막 개행도 해시에 포함해 경계 공백 변경도 감지한다.
        normalized = content.replace("\r\n", "\n")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def detect_conflict_by_hash(self, current_hash: str, last_synced_hash: str) -> bool:
        """
        해시 기반 변경 감지

        Args:
            current_hash: 현재 파일의 해시
            last_synced_hash: 마지막 동기화 시점의 해시

        Returns:
            bool: 변경됨(True) / 변경없음(False)
        """
        return not last_synced_hash or current_hash != last_synced_hash

    def detect_conflict_3way(
        self,
        file_id: str,
        external_path: str,
        local_hash: str,
        remote_hash: str,
        last_synced_hash: Optional[str],
    ) -> Optional[SyncConflict]:
        """
        3-way 충돌 감지 (Step 4 핵심 로직)

        충돌 시나리오:
        1. 양쪽 모두 변경됨 (local != last_synced AND remote != last_synced) -> CONFLICT
        2. 로컬만 변경됨 -> 충돌 아님 (Push 필요)
        3. 원격만 변경됨 -> 충돌 아님 (Pull 필요)
        4. 양쪽 동일 -> 충돌 아님

        Args:
            file_id: 내부 파일 ID (absolute path)
            external_path: 외부 파일 경로
            local_hash: 현재 로컬 파일 해시
            remote_hash: 현재 원격 파일 해시
            last_synced_hash: 마지막 동기화 시점 해시

        Returns:
            SyncConflict object if conflict detected, None otherwise
        """
        # 초기 동기화 (last_synced_hash 없음)
        if not last_synced_hash:
            if local_hash != remote_hash:
                logger.info(
                    "First sync detected with different content. Treating as remote-wins."
                )
                return None  # 초기 동기화는 충돌로 간주하지 않음
            return None

        # 양쪽 모두 변경되지 않음
        if local_hash == remote_hash == last_synced_hash:
            return None

        # 로컬만 변경됨
        local_changed = local_hash != last_synced_hash
        remote_changed = remote_hash != last_synced_hash

        if local_changed and not remote_changed:
            logger.debug("Local-only change detected. Push required.")
            return None

        # 원격만 변경됨
        if remote_changed and not local_changed:
            logger.debug("Remote-only change detected. Pull required.")
            return None

        # 양쪽 모두 변경됨 -> 충돌!
        if local_changed and remote_changed:
            logger.warning(
                f"⚠️ CONFLICT DETECTED: Both local and remote modified since last sync. "
                f"Local: {local_hash[:8]}, Remote: {remote_hash[:8]}, Last: {last_synced_hash[:8]}"
            )

            # SyncConflict 객체 생성 및 반환
            return SyncConflict(
                file_id=file_id,
                external_path=external_path,
                tool_type=self.tool_type,
                conflict_type=SyncConflictType.CONTENT_MISMATCH,
                local_hash=local_hash,
                remote_hash=remote_hash,
            )

        return None

    async def _handle_conflict(self, conflict: SyncConflict) -> bool:
        """
        [공통] 충돌 발생 시 충돌 레코드를 JSONL 파일에 저장하고 False를 반환한다.
        실제 해결은 ConflictResolutionService에서 담당한다.
        """
        logger.warning(
            "Conflict detected for %s: Local(%s) vs Remote(%s)",
            get_safe_file_id(conflict.file_id),
            (conflict.local_hash or "")[:8],
            (conflict.remote_hash or "")[:8],
        )
        try:
            _SYNC_LOG_DIR.mkdir(parents=True, exist_ok=True)
            local_hash_safe = conflict.local_hash[:16] if conflict.local_hash else ""
            remote_hash_safe = conflict.remote_hash[:16] if conflict.remote_hash else ""
            record = {
                "conflict_id": conflict.conflict_id,
                "file_id": get_safe_file_id(conflict.file_id),
                "external_path": conflict.external_path,
                "tool_type": (
                    conflict.tool_type.value
                    if hasattr(conflict.tool_type, "value")
                    else str(conflict.tool_type)
                ),
                "conflict_type": (
                    conflict.conflict_type.value
                    if hasattr(conflict.conflict_type, "value")
                    else str(conflict.conflict_type)
                ),
                "local_hash": local_hash_safe,
                "remote_hash": remote_hash_safe,
                "detected_at": datetime.now().isoformat(),
            }
            with open(_CONFLICT_RECORD_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            meta = build_meta({"action": "_handle_conflict"})
            log_agent_error(logger, "Failed to persist conflict record", exc, meta)
        return False

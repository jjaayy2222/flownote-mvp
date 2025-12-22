# backend/services/sync_service.py

"""
Sync Service Abstraction
외부 도구 동기화 서비스의 기본 인터페이스 정의
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Any
from datetime import datetime

from backend.models.external_sync import (
    ExternalToolConnection,
    ExternalFileMapping,
    SyncStatus,
)
from backend.models.conflict import SyncConflict, ResolutionMethod

logger = logging.getLogger(__name__)


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
        pass

    @abstractmethod
    async def sync_all(self) -> List[SyncConflict]:
        """전체 동기화 수행"""
        pass

    @abstractmethod
    async def pull_file(self, external_id: str) -> Optional[str]:
        """외부 파일 가져오기 (내용 반환)"""
        pass

    @abstractmethod
    async def push_file(self, internal_id: str, content: str) -> bool:
        """내부 파일을 외부로 내보내기"""
        pass

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
        local_hash: str,
        remote_hash: str,
        last_synced_hash: Optional[str],
    ) -> Optional[SyncConflict]:
        """
        3-way 충돌 감지 (Step 4 핵심 로직)

        충돌 시나리오:
        1. 양쪽 모두 변경됨 (local != last_synced AND remote != last_synced)
        2. 로컬만 변경됨 -> 충돌 아님 (Push 필요)
        3. 원격만 변경됨 -> 충돌 아님 (Pull 필요)
        4. 양쪽 동일 -> 충돌 아님

        Args:
            local_hash: 현재 로컬 파일 해시
            remote_hash: 현재 원격 파일 해시
            last_synced_hash: 마지막 동기화 시점 해시

        Returns:
            SyncConflict if conflict detected, None otherwise
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
            # SyncConflict 객체는 호출자가 생성 (file_id, external_path 필요)
            # 여기서는 충돌 여부만 반환
            return True  # Placeholder: 실제로는 SyncConflict 객체 반환 필요

        return None

    async def _handle_conflict(self, conflict: SyncConflict) -> bool:
        """
        [공통] 충돌 발생 시 처리 (DB 기록 등)
        실제 해결은 ConflictResolutionService에서 담당
        """
        logger.warning(
            f"Conflict detected for {conflict.file_id}: "
            f"Local({conflict.local_hash}) vs Remote({conflict.remote_hash})"
        )
        # TODO: DB에 충돌 레코드 저장
        return False

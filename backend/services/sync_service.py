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
        return (not last_synced_hash) or (current_hash != last_synced_hash)

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

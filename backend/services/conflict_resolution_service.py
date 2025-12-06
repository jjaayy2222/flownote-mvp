# backend/services/conflict_resolution_service.py

"""
Conflict Resolution Service
동기화 충돌(SyncConflict)을 감지하고 전략에 따라 해결하는 서비스
"""

import logging
from typing import Optional, Any
from datetime import datetime

from backend.models.conflict import (
    SyncConflict,
    ConflictResolution,
    ResolutionStrategy,
    ResolutionMethod,
    ResolutionStatus,
    ConflictResolutionLog,
)
from backend.services.sync_service import SyncServiceBase
from backend.mcp.sync_map_manager import SyncMapManager

logger = logging.getLogger(__name__)


class ConflictResolutionService:
    """
    충돌 해결 서비스
    - 다양한 전략(Strategy)에 따라 파일 동기화 충돌을 해결
    - 해결 결과를 MapManager에 반영하고 로그를 남김
    """

    def __init__(self, sync_service: SyncServiceBase, map_manager: SyncMapManager):
        self.sync_service = sync_service
        self.map_manager = map_manager

    async def resolve_conflict(
        self, conflict: SyncConflict, strategy: ResolutionStrategy
    ) -> ConflictResolution:
        """
        충돌 해결 메인 진입점

        Args:
            conflict: 해결할 충돌 객체
            strategy: 적용할 해결 전략

        Returns:
            ConflictResolution: 해결 결과
        """
        logger.info(
            f"Resolving conflict {conflict.conflict_id} with strategy {strategy.method}"
        )

        try:
            # 전략에 따른 해결 로직 실행
            if strategy.method == ResolutionMethod.MANUAL_OVERRIDE:
                success = await self._resolve_manual(conflict, strategy)
            elif strategy.method == ResolutionMethod.AUTO_BY_CONTEXT:
                # MVP: AUTO_BY_CONTEXT를 'Remote Wins'로 간주 (단순화)
                success = await self._resolve_remote_wins(conflict)
            elif strategy.method == ResolutionMethod.AUTO_BY_CONFIDENCE:
                # MVP: AUTO_BY_CONFIDENCE를 'Remote Wins'로 간주 (단순화)
                success = await self._resolve_remote_wins(conflict)
            else:
                logger.warning(f"Unsupported resolution method: {strategy.method}")
                success = False

            # 결과 객체 생성 및 즉시 반환 (Inline)
            status = ResolutionStatus.RESOLVED if success else ResolutionStatus.FAILED
            return ConflictResolution(
                conflict_id=conflict.conflict_id,
                status=status,
                strategy=strategy.model_dump(),
                resolved_by="system",
                resolved_at=datetime.now(),
                notes=(
                    f"Resolved via {strategy.method}"
                    if success
                    else "Resolution failed"
                ),
            )

        except Exception as e:
            logger.error(
                f"Error resolving conflict {conflict.conflict_id}: {e}", exc_info=True
            )
            return ConflictResolution(
                conflict_id=conflict.conflict_id,
                status=ResolutionStatus.FAILED,
                strategy=strategy.model_dump(),
                resolved_by="system",
                resolved_at=datetime.now(),  # Fix: resolved_at 추가
                notes=str(e),
            )

    async def _resolve_manual(
        self, conflict: SyncConflict, strategy: ResolutionStrategy
    ) -> bool:
        """
        수동 해결: 사용자가 제공한 값을 덮어씀

        Note: MVP에서는 미구현 상태. File Service 및 UI 통합 필요.
        """
        raise NotImplementedError(
            "Manual conflict resolution requires File Service integration. "
            "This feature will be implemented in a future version."
        )

    async def _resolve_remote_wins(self, conflict: SyncConflict) -> bool:
        """외부(Obsidian) 데이터로 로컬 파일을 덮어씀"""
        # 1. 외부 파일 Pull
        remote_content = await self.sync_service.pull_file(conflict.external_path)
        if remote_content is None:
            logger.warning(
                f"Remote-wins resolution failed: pull_file returned None "
                f"for external_path={conflict.external_path}, conflict_id={conflict.conflict_id}"
            )
            return False

        # 2. 로컬 파일 저장 (File Service 필요)
        # Note: MVP에서는 File Service가 아직 주입되지 않았으므로 NotImplementedError 발생
        raise NotImplementedError(
            "Local file save operation requires File Service integration. "
            f"Remote content retrieved successfully for {conflict.external_path}, "
            "but cannot persist to local storage yet."
        )

        # 3. 매핑 정보 업데이트 (File Service 구현 후 활성화)
        # new_hash = self.sync_service.calculate_file_hash(remote_content)
        # self._update_mapping(conflict, new_hash)
        # return True

    def _update_mapping(self, conflict: SyncConflict, new_hash: str):
        """해결 후 SyncMapManager 업데이트"""
        self.map_manager.update_mapping(
            internal_id=conflict.file_id,
            external_path=conflict.external_path,
            tool_type=conflict.tool_type,
            current_hash=new_hash,
        )

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
    - SyncService는 런타임에 주입받거나 찾아서 사용 (MVP: 생성자 주입)
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
                # MVP: AUTO_BY_CONTEXT를 'Local Wins'로 간주 (단순화)
                success = await self._resolve_local_wins(conflict)
            elif strategy.method == ResolutionMethod.AUTO_BY_CONFIDENCE:
                # MVP: AUTO_BY_CONFIDENCE를 'Remote Wins'로 간주 (단순화)
                success = await self._resolve_remote_wins(conflict)
            else:
                logger.warning(f"Unsupported resolution method: {strategy.method}")
                success = False

            # 결과 객체 생성
            status = ResolutionStatus.RESOLVED if success else ResolutionStatus.FAILED
            resolution = ConflictResolution(
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

            return resolution

        except Exception as e:
            logger.error(
                f"Error resolving conflict {conflict.conflict_id}: {e}", exc_info=True
            )
            return ConflictResolution(
                conflict_id=conflict.conflict_id,
                status=ResolutionStatus.FAILED,
                strategy=strategy.model_dump(),
                resolved_by="system",
                notes=str(e),
            )

    async def _resolve_manual(
        self, conflict: SyncConflict, strategy: ResolutionStrategy
    ) -> bool:
        """
        수동 해결: 사용자가 제공한 값을 덮어씀 (구현 예정)
        MVP에서는 'recommended_value'에 전체 텍스트가 있다고 가정하거나,
        단순히 어떤 쪽을 선택했는지(Flag)로 판단할 수 있음.
        """
        # TODO: Implement manual content merge/overwrite logic
        logger.info("Manual resolution not fully implemented yet.")
        return False

    async def _resolve_local_wins(self, conflict: SyncConflict) -> bool:
        """로컬(FlowNote) 데이터로 외부 파일을 덮어씀"""
        # 1. 로컬 파일 내용 읽기 (File Service 필요, MVP에서는 생략하고 성공 가정)
        # local_content = await self.file_service.read(conflict.file_id)
        local_content = "Mock Local Content"  # Temporary

        # 2. 외부로 Push
        success = await self.sync_service.push_file(conflict.file_id, local_content)

        if success:
            # 3. 매핑 정보 업데이트 (Hash 갱신)
            new_hash = self.sync_service.calculate_file_hash(local_content)
            self._update_mapping(conflict, new_hash)

        return success

    async def _resolve_remote_wins(self, conflict: SyncConflict) -> bool:
        """외부(Obsidian) 데이터로 로컬 파일을 덮어씀"""
        # 1. 외부 파일 Pull
        remote_content = await self.sync_service.pull_file(conflict.external_path)
        if remote_content is None:
            return False

        # 2. 로컬 파일 저장 (File Service 필요)
        # await self.file_service.save(conflict.file_id, remote_content)
        # logger.info(f"Overwrote local file {conflict.file_id} with remote content")

        # 3. 매핑 정보 업데이트
        new_hash = self.sync_service.calculate_file_hash(remote_content)
        self._update_mapping(conflict, new_hash)

        return True

    def _update_mapping(self, conflict: SyncConflict, new_hash: str):
        """해결 후 SyncMapManager 업데이트"""
        self.map_manager.update_mapping(
            internal_id=conflict.file_id,
            external_path=conflict.external_path,
            tool_type=conflict.tool_type,
            current_hash=new_hash,
        )

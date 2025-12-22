# backend/services/conflict_resolution_service.py

"""
Conflict Resolution Service
동기화 충돌(SyncConflict)을 감지하고 전략에 따라 해결하는 서비스
"""

import logging
import os
import shutil
from typing import Optional
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from backend.models.conflict import (
    SyncConflict,
    SyncConflictType,
    ConflictResolution,
    ResolutionStrategy,
    ResolutionMethod,
    ResolutionStatus,
)
from backend.models.external_sync import ExternalSyncLog, SyncStatus, ExternalToolType
from backend.services.sync_service import SyncServiceBase
from backend.mcp.sync_map_manager import SyncMapManager
from backend.services.ignore_manager import ignore_manager

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
            elif strategy.method in (
                ResolutionMethod.AUTO_BY_CONTEXT,
                ResolutionMethod.AUTO_BY_CONFIDENCE,
            ):
                # MVP: Rename 전략 사용 (양쪽 모두 보존)
                success = await self._resolve_rename(conflict)
            else:
                logger.warning(f"Unsupported resolution method: {strategy.method}")
                success = False

            # 결과 객체 생성 및 즉시 반환
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

        except NotImplementedError as e:
            # File Service 미구현으로 인한 예외를 우아하게 처리
            logger.warning(
                f"Resolution not yet implemented for {conflict.conflict_id}: {e}"
            )
            return ConflictResolution(
                conflict_id=conflict.conflict_id,
                status=ResolutionStatus.FAILED,
                strategy=strategy.model_dump(),
                resolved_by="system",
                resolved_at=datetime.now(),
                notes=f"Not implemented: {str(e)}",
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
                resolved_at=datetime.now(),
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
            "Manual conflict resolution requires File Service integration."
        )

    async def _resolve_rename(self, conflict: SyncConflict) -> bool:
        """
        Rename 전략: 로컬 파일을 백업하고 원격 파일을 가져옴

        Step 4 핵심 구현:
        1. 로컬 파일을 `{filename}_conflict_{timestamp}.md`로 백업
        2. 원격 파일을 원래 위치에 Pull
        3. 충돌 로그 기록
        """
        try:
            # 1. 로컬 파일 경로 확인
            local_path = Path(conflict.file_id)  # file_id = absolute path
            if not local_path.exists():
                logger.error(f"Local file not found: {local_path}")
                return False

            # 2. 백업 파일명 생성
            timestamp = int(datetime.now().timestamp())
            stem = local_path.stem
            suffix = local_path.suffix
            backup_name = f"{stem}_conflict_{timestamp}{suffix}"
            backup_path = local_path.parent / backup_name

            # 3. 로컬 파일 백업 (Loop Prevention)
            # NOTE: ignore_manager.add는 백업 성공 후에만 호출하여 실패 시 무시 방지
            try:
                shutil.copy2(str(local_path), str(backup_path))
            except OSError as e:
                # 부분 백업 파일 정리 (손상된 파일이 남지 않도록)
                # NOTE: 정리 실패는 원본 에러를 가리지 않도록 무시 (best-effort cleanup)
                try:
                    backup_path.unlink(missing_ok=True)
                except OSError:
                    # 정리 실패는 무시 (권한 문제, 읽기 전용 파일 시스템 등)
                    pass

                logger.exception(
                    "⚠️ Failed to create conflict backup '%s'. Partial file cleanup attempted.",
                    backup_path,
                )
                return False
            else:
                # 백업 성공 시에만 ignore 등록
                ignore_manager.add(str(backup_path))
                logger.info(f"✅ Created conflict backup: {backup_path.name}")

            # 4. 원격 파일 Pull
            remote_content = await self.sync_service.pull_file(conflict.external_path)
            if remote_content is None:
                logger.error(f"Failed to pull remote file: {conflict.external_path}")
                return False

            # 5. 원격 내용으로 로컬 파일 덮어쓰기 (Loop Prevention)
            ignore_manager.add(str(local_path))
            local_path.write_text(remote_content, encoding="utf-8")
            logger.info(
                f"✅ Overwrote local file with remote content: {local_path.name}"
            )

            # 6. 해시 업데이트
            new_hash = self.sync_service.calculate_file_hash(remote_content)
            self._update_mapping(conflict, new_hash)

            # 7. 충돌 로그 기록
            self._log_conflict_resolution(
                conflict=conflict,
                action="rename_backup",
                status=SyncStatus.COMPLETED,
                message=f"Backup created: {backup_name}, remote content applied",
            )

            return True

        except Exception as e:
            logger.exception(f"Error in rename resolution: {e}")
            self._log_conflict_resolution(
                conflict=conflict,
                action="rename_backup",
                status=SyncStatus.FAILED,
                message=str(e),
            )
            return False

    def _log_conflict_resolution(
        self,
        conflict: SyncConflict,
        action: str,
        status: SyncStatus,
        message: str,
    ):
        """
        충돌 해결 이력을 ExternalSyncLog에 기록

        Step 4 요구사항: 충돌 이력 로깅
        """
        # 로그 ID를 유니크하게 생성 (동일 충돌 재시도 시 ID 충돌 방지, 충분한 엔트로피 확보)
        uuid_suffix = uuid4().hex  # 32자 전체를 사용하여 충돌 가능성 최소화
        log_entry = ExternalSyncLog(
            id=f"sync_log_{conflict.conflict_id}_{uuid_suffix}",
            timestamp=datetime.now(),
            tool_type=conflict.tool_type,
            action=action,
            file_path=conflict.external_path,
            status=status,
            message=message,
            details={
                "conflict_id": conflict.conflict_id,
                "conflict_type": conflict.conflict_type.value,
                "local_hash": conflict.local_hash,
                "remote_hash": conflict.remote_hash,
            },
        )

        # TODO: JSONL 파일에 기록 (PathConfig 사용)
        logger.info(f"📝 Conflict resolution logged: {log_entry.id}")

    async def _resolve_remote_wins(self, conflict: SyncConflict) -> bool:
        """외부(Obsidian) 데이터로 로컬 파일을 덮어씀 (Deprecated: use _resolve_rename)"""
        # 1. 외부 파일 Pull
        remote_content = await self.sync_service.pull_file(conflict.external_path)
        if remote_content is None:
            logger.warning(
                f"Remote-wins resolution failed: pull_file returned None "
                f"for external_path={conflict.external_path}, conflict_id={conflict.conflict_id}"
            )
            return False

        # 2. 로컬 파일 저장 (File Service 필요)
        raise NotImplementedError(
            f"Local file save operation requires File Service integration. "
            f"Remote content retrieved for {conflict.external_path}, but cannot persist locally."
        )

    def _update_mapping(self, conflict: SyncConflict, new_hash: str):
        """해결 후 SyncMapManager 업데이트"""
        self.map_manager.update_mapping(
            internal_id=conflict.file_id,
            external_path=conflict.external_path,
            tool_type=conflict.tool_type,
            current_hash=new_hash,
        )

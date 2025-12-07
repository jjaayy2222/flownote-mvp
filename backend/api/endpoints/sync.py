# backend/api/endpoints/sync.py

"""
Sync API Endpoints
외부 도구(Obsidian)와의 동기화 및 충돌 해결 API

Note: MVP에서는 Obsidian만 지원합니다.
"""

import logging
from functools import lru_cache
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from backend.models.external_sync import ExternalToolType
from backend.models.conflict import (
    SyncConflict,
    ConflictResolution,
    ResolutionStrategy,
    ResolutionStatus,
)
from backend.services.sync_service import SyncServiceBase
from backend.services.conflict_resolution_service import ConflictResolutionService
from backend.mcp.sync_map_manager import SyncMapManager
from backend.mcp.obsidian_server import ObsidianSyncService
from backend.config.mcp_config import mcp_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["Synchronization"])


# ==========================================
# Request/Response Models
# ==========================================


class SyncStatusResponse(BaseModel):
    """동기화 상태 응답"""

    tool_type: ExternalToolType
    is_connected: bool
    is_watching: bool
    last_sync_at: Optional[str] = None
    total_mappings: int


class ConflictListResponse(BaseModel):
    """충돌 목록 응답"""

    conflicts: List[SyncConflict]
    total_count: int


class ConflictResolveRequest(BaseModel):
    """충돌 해결 요청"""

    strategy: ResolutionStrategy


class ConflictResolveResponse(BaseModel):
    """충돌 해결 응답"""

    resolution: ConflictResolution
    success: bool


# ==========================================
# Dependency Injection (FastAPI Best Practice)
# ==========================================


@lru_cache
def get_sync_service() -> SyncServiceBase:
    """
    동기화 서비스 싱글톤 (FastAPI Dependency)

    Note: MVP에서는 Obsidian만 지원
    """
    return ObsidianSyncService(mcp_config.obsidian)


@lru_cache
def get_map_manager() -> SyncMapManager:
    """매핑 매니저 싱글톤 (FastAPI Dependency)"""
    return SyncMapManager()


def get_resolution_service(
    sync_service: SyncServiceBase = Depends(get_sync_service),
    map_manager: SyncMapManager = Depends(get_map_manager),
) -> ConflictResolutionService:
    """
    충돌 해결 서비스 팩토리 (FastAPI Dependency)

    Note: @lru_cache 제거 (FastAPI가 요청 단위 캐싱 자동 처리).
    Depends()로 주입받아 DI 시맨틱 유지 (overrides, async 지원).
    """
    return ConflictResolutionService(sync_service=sync_service, map_manager=map_manager)


# ==========================================
# API Endpoints
# ==========================================


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    sync_service: SyncServiceBase = Depends(get_sync_service),
) -> dict:
    """
    수동 동기화 트리거 (전체 파일)

    Note: MVP에서는 Obsidian 전체 동기화만 지원합니다.
    """
    logger.info("Sync trigger requested for Obsidian (전체)")

    try:
        # 연결 확인
        if not await sync_service.connect():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Failed to connect to Obsidian vault",
            )

        # 동기화 수행
        conflicts = await sync_service.sync_all()

        return {
            "message": "Sync triggered successfully",
            "tool_type": ExternalToolType.OBSIDIAN,
            "conflicts_detected": len(conflicts),
            "conflicts": [c.model_dump() for c in conflicts],
        }

    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Sync operation not fully implemented: {str(e)}",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync trigger failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}",
        ) from e


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    sync_service: SyncServiceBase = Depends(get_sync_service),
    map_manager: SyncMapManager = Depends(get_map_manager),
) -> SyncStatusResponse:
    """
    동기화 상태 조회 (Obsidian)
    """
    try:
        is_connected = await sync_service.connect()

        # Obsidian specific status
        is_watching = False
        if isinstance(sync_service, ObsidianSyncService):
            is_watching = sync_service.is_watching

        return SyncStatusResponse(
            tool_type=ExternalToolType.OBSIDIAN,
            is_connected=is_connected,
            is_watching=is_watching,
            last_sync_at=None,  # TODO: Track last sync timestamp
            total_mappings=map_manager.get_total_count(),
        )

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Status check failed: {str(e)}",
        ) from e


@router.get("/conflicts", response_model=ConflictListResponse)
async def get_conflicts(
    sync_service: SyncServiceBase = Depends(get_sync_service),
) -> ConflictListResponse:
    """
    현재 감지된 충돌 목록 조회

    Note: MVP에서는 DB 저장 없이 실시간 스캔 결과만 반환.
    TODO: 충돌 캐싱으로 반복 스캔 비용 절감 필요.
    """
    try:
        conflicts = await sync_service.sync_all()

        return ConflictListResponse(conflicts=conflicts, total_count=len(conflicts))

    except Exception as e:
        logger.error(f"Failed to get conflicts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conflict retrieval failed: {str(e)}",
        ) from e


@router.post("/conflicts/{conflict_id}/resolve", response_model=ConflictResolveResponse)
async def resolve_conflict(
    conflict_id: str,
    request: ConflictResolveRequest,
    sync_service: SyncServiceBase = Depends(get_sync_service),
    resolution_service: ConflictResolutionService = Depends(get_resolution_service),
) -> ConflictResolveResponse:
    """
    충돌 해결

    - **conflict_id**: 해결할 충돌 ID
    - **strategy**: 해결 전략 (MANUAL_OVERRIDE, AUTO_BY_CONTEXT 등)

    Note: MVP에서는 실시간 스캔으로 충돌을 찾습니다.
    TODO: 충돌 DB 저장 후 ID로 직접 조회하도록 개선 필요.
    """
    logger.info(
        f"Resolving conflict {conflict_id} with strategy {request.strategy.method}"
    )

    try:
        # 1. 충돌 조회 (MVP: 실시간 스캔에서 찾기)
        conflicts = await sync_service.sync_all()

        conflict = next((c for c in conflicts if c.conflict_id == conflict_id), None)
        if not conflict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conflict {conflict_id} not found",
            )

        # 2. 해결 수행
        resolution = await resolution_service.resolve_conflict(
            conflict, request.strategy
        )

        return ConflictResolveResponse(
            resolution=resolution,
            success=resolution.status == ResolutionStatus.RESOLVED,
        )

    except HTTPException:
        raise
    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Resolution strategy not implemented: {str(e)}",
        ) from e
    except Exception as e:
        logger.error(f"Conflict resolution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resolution failed: {str(e)}",
        ) from e

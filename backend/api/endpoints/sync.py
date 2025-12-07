# backend/api/endpoints/sync.py

"""
Sync API Endpoints
외부 도구(Obsidian 등)와의 동기화 및 충돌 해결 API
"""

import logging
import threading
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
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


class SyncTriggerRequest(BaseModel):
    """동기화 트리거 요청"""

    tool_type: ExternalToolType = Field(..., description="동기화할 외부 도구")
    file_id: Optional[str] = Field(
        None, description="특정 파일 ID (None이면 전체 동기화)"
    )


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
# Dependency Injection (Thread-safe Singleton)
# ==========================================

_sync_service: Optional[SyncServiceBase] = None
_map_manager: Optional[SyncMapManager] = None
_resolution_service: Optional[ConflictResolutionService] = None
_lock = threading.Lock()


def get_sync_service() -> SyncServiceBase:
    """동기화 서비스 싱글톤 (Thread-safe)"""
    global _sync_service
    if _sync_service is None:
        with _lock:
            # Double-checked locking
            if _sync_service is None:
                _sync_service = ObsidianSyncService(mcp_config.obsidian)
    return _sync_service


def get_map_manager() -> SyncMapManager:
    """매핑 매니저 싱글톤 (Thread-safe)"""
    global _map_manager
    if _map_manager is None:
        with _lock:
            if _map_manager is None:
                _map_manager = SyncMapManager()
    return _map_manager


def get_resolution_service() -> ConflictResolutionService:
    """충돌 해결 서비스 싱글톤 (Thread-safe)"""
    global _resolution_service
    if _resolution_service is None:
        with _lock:
            if _resolution_service is None:
                _resolution_service = ConflictResolutionService(
                    sync_service=get_sync_service(), map_manager=get_map_manager()
                )
    return _resolution_service


# ==========================================
# API Endpoints
# ==========================================


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(request: SyncTriggerRequest) -> dict:
    """
    수동 동기화 트리거

    - **tool_type**: 동기화할 외부 도구 (obsidian, notion 등)
    - **file_id**: 특정 파일만 동기화 (None이면 전체)
    """
    logger.info(
        f"Sync trigger requested for {request.tool_type}, file_id={request.file_id}"
    )

    try:
        sync_service = get_sync_service()

        # 연결 확인
        if not await sync_service.connect():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to connect to {request.tool_type}",
            )

        # 동기화 수행
        conflicts = await sync_service.sync_all()

        return {
            "message": "Sync triggered successfully",
            "tool_type": request.tool_type,
            "conflicts_detected": len(conflicts),
            "conflicts": [c.model_dump() for c in conflicts],
        }

    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Sync operation not fully implemented: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Sync trigger failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}",
        )


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    tool_type: ExternalToolType = ExternalToolType.OBSIDIAN,
) -> SyncStatusResponse:
    """
    동기화 상태 조회

    - **tool_type**: 조회할 외부 도구
    """
    try:
        sync_service = get_sync_service()
        map_manager = get_map_manager()

        is_connected = await sync_service.connect()

        # Obsidian specific status
        is_watching = False
        if isinstance(sync_service, ObsidianSyncService):
            is_watching = sync_service.is_watching

        return SyncStatusResponse(
            tool_type=tool_type,
            is_connected=is_connected,
            is_watching=is_watching,
            last_sync_at=None,  # TODO: Track last sync timestamp
            total_mappings=map_manager.get_total_count(),  # Use public method
        )

    except Exception as e:
        logger.error(f"Failed to get sync status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Status check failed: {str(e)}",
        )


@router.get("/conflicts", response_model=ConflictListResponse)
async def get_conflicts() -> ConflictListResponse:
    """
    현재 감지된 충돌 목록 조회

    Note: MVP에서는 DB 저장 없이 실시간 스캔 결과만 반환
    """
    try:
        sync_service = get_sync_service()
        conflicts = await sync_service.sync_all()

        return ConflictListResponse(conflicts=conflicts, total_count=len(conflicts))

    except Exception as e:
        logger.error(f"Failed to get conflicts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conflict retrieval failed: {str(e)}",
        )


@router.post("/conflicts/{conflict_id}/resolve", response_model=ConflictResolveResponse)
async def resolve_conflict(
    conflict_id: str, request: ConflictResolveRequest
) -> ConflictResolveResponse:
    """
    충돌 해결

    - **conflict_id**: 해결할 충돌 ID
    - **strategy**: 해결 전략 (MANUAL_OVERRIDE, AUTO_BY_CONTEXT 등)
    """
    logger.info(
        f"Resolving conflict {conflict_id} with strategy {request.strategy.method}"
    )

    try:
        # 1. 충돌 조회 (MVP: 실시간 스캔에서 찾기)
        sync_service = get_sync_service()
        conflicts = await sync_service.sync_all()

        conflict = next((c for c in conflicts if c.conflict_id == conflict_id), None)
        if not conflict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conflict {conflict_id} not found",
            )

        # 2. 해결 수행
        resolution_service = get_resolution_service()
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
        )
    except Exception as e:
        logger.error(f"Conflict resolution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Resolution failed: {str(e)}",
        )

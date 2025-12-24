# backend/api/endpoints/sync.py

"""
External Sync API Endpoints

MCP 서버 및 Obsidian 동기화 상태 모니터링 API
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import logging

from backend.services.obsidian_sync import ObsidianSyncService
from backend.config.mcp_config import get_mcp_config
from backend.models.external_sync import SyncStatus, ExternalToolType
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


# ==========================================
# Response Models
# ==========================================


class SyncStatusResponse(BaseModel):
    """동기화 상태 응답"""

    connected: bool
    vault_path: Optional[str]
    last_sync: Optional[datetime]
    sync_interval: int
    enabled: bool
    file_count: int


class MCPStatusResponse(BaseModel):
    """MCP 서버 상태 응답"""

    running: bool
    active_clients: List[str]
    tools_registered: List[str]
    resources_registered: List[str]


class ConflictLogResponse(BaseModel):
    """충돌 로그 응답"""

    conflict_id: str
    timestamp: datetime
    file_path: str
    conflict_type: str
    local_hash: str
    remote_hash: str
    status: str
    resolution_method: Optional[str]
    notes: Optional[str]


# ==========================================
# Endpoints
# ==========================================


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status():
    """
    Obsidian 동기화 상태 조회

    Returns:
        SyncStatusResponse: 동기화 상태 정보
    """
    try:
        config = get_mcp_config()

        # Vault 경로 확인
        vault_path = Path(config.obsidian.vault_path) if config.obsidian.vault_path else None
        connected = vault_path is not None and vault_path.exists() and vault_path.is_dir()

        # 파일 개수 계산
        file_count = 0
        if connected:
            file_count = len(list(vault_path.rglob("*.md")))

        # TODO: 실제 last_sync는 SyncMapManager에서 조회
        return SyncStatusResponse(
            connected=connected,
            vault_path=str(vault_path) if vault_path else None,
            last_sync=datetime.now() if connected else None,  # Placeholder
            sync_interval=config.obsidian.sync_interval,
            enabled=config.obsidian.enabled,
            file_count=file_count,
        )
    except Exception as e:
        logger.error(f"Failed to get sync status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/status", response_model=MCPStatusResponse)
async def get_mcp_status():
    """
    MCP 서버 상태 조회

    Returns:
        MCPStatusResponse: MCP 서버 상태 정보
    """
    try:
        # TODO: 실제 MCP 서버 상태는 backend.mcp.server에서 조회
        # 현재는 설정 기반으로 응답
        config = get_mcp_config()

        # Placeholder 데이터
        return MCPStatusResponse(
            running=True,  # TODO: 실제 서버 실행 상태 확인
            active_clients=["Claude Desktop"],  # TODO: 실제 클라이언트 목록
            tools_registered=[
                "classify_content",
                "search_notes",
                "get_automation_stats",
            ],
            resources_registered=[
                "flownote://para/projects",
                "flownote://dashboard/summary",
            ],
        )
    except Exception as e:
        logger.error(f"Failed to get MCP status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conflicts", response_model=List[ConflictLogResponse])
async def get_conflicts(
    limit: int = 50,
    status: Optional[str] = None,
):
    """
    충돌 이력 조회

    Args:
        limit: 조회할 최대 개수
        status: 필터링할 상태 (resolved, pending 등)

    Returns:
        List[ConflictLogResponse]: 충돌 로그 목록
    """
    try:
        # TODO: 실제로는 ExternalSyncLog에서 충돌 이력 조회
        # 현재는 빈 목록 반환
        conflicts = []

        if status:
            conflicts = [c for c in conflicts if c["status"] == status]

        return conflicts[:limit]
    except Exception as e:
        logger.error(f"Failed to get conflicts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    resolution_method: str,  # "local", "remote", "both"
):
    """
    충돌 해결

    Args:
        conflict_id: 충돌 ID
        resolution_method: 해결 방법 (local, remote, both)

    Returns:
        dict: 해결 결과
    """
    try:
        # TODO: ConflictResolutionService를 통해 실제 충돌 해결
        logger.info(
            f"Resolving conflict {conflict_id} with method: {resolution_method}"
        )

        return {
            "conflict_id": conflict_id,
            "status": "resolved",
            "method": resolution_method,
            "timestamp": datetime.now(),
        }
    except Exception as e:
        logger.error(f"Failed to resolve conflict: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

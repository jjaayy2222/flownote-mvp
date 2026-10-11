# backend/api/endpoints/sync.py

"""
External Sync API Endpoints

MCP 서버 및 Obsidian 동기화 상태 모니터링 API
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agent.error_utils import log_agent_error
from backend.config import PathConfig
from backend.config.mcp_config import mcp_config
from backend.mcp.sync_map_manager import SyncMapManager
from backend.models.conflict import ResolutionMethod
from backend.models.conflict import ResolutionStrategy as DomainResolutionStrategy
from backend.models.conflict import SyncConflict
from backend.models.external_sync import (
    ConnectionConfig,
    ExternalToolConnection,
    ExternalToolType,
)
from backend.services.conflict_resolution_service import ConflictResolutionService
from backend.services.diff_service import generate_diff
from backend.services.obsidian_sync import ObsidianSyncService

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


class ResolutionStrategy(str, Enum):
    """충돌 해결 전략"""

    KEEP_LOCAL = "keep_local"
    KEEP_REMOTE = "keep_remote"
    KEEP_BOTH = "keep_both"


class ConflictDiffResponse(BaseModel):
    """Diff 조회 응답"""

    conflict_id: str
    local_content: str
    remote_content: str
    diff: Dict[str, Any]
    file_type: str


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
        config = mcp_config

        # Vault 경로 확인
        vault_path = (
            Path(config.obsidian.vault_path) if config.obsidian.vault_path else None
        )
        connected = (
            vault_path is not None and vault_path.exists() and vault_path.is_dir()
        )

        # 파일 개수 계산
        file_count = 0
        if connected:
            file_count = len(list(vault_path.rglob("*.md")))

        # last_sync: 향후 SyncMapManager에서 조회될 시점까지 None 반환
        # (프론트엔드는 None일 때 "-" 또는 "연결 대기 중" 등으로 표시 권장)
        return SyncStatusResponse(
            connected=connected,
            vault_path=str(vault_path) if vault_path else None,
            last_sync=None,
            sync_interval=config.obsidian.sync_interval,
            enabled=config.obsidian.enabled,
            file_count=file_count,
        )
    except Exception as e:
        log_agent_error(
            logger, f"Failed to get sync status: {e}", e, include_traceback=True
        )
        raise HTTPException(
            status_code=500,
            detail="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from e


@router.get("/mcp/status", response_model=MCPStatusResponse)
async def get_mcp_status():
    """
    MCP 서버 상태 조회

    Returns:
        MCPStatusResponse: MCP 서버 상태 정보.
        실제 연결된 클라이언트 목록은 향후 MCP 런타임 연동 시 제공된다.
    """
    try:
        config = mcp_config

        # 등록된 툴리스트는 설정 기반으로 구성함 (하드코딩 제거)
        configured_tools = getattr(config, "registered_tools", None)
        registered_tools = (
            configured_tools
            if configured_tools is not None
            else [
                "classify_content",
                "search_notes",
                "get_automation_stats",
            ]
        )

        configured_resources = getattr(config, "registered_resources", None)
        registered_resources = (
            configured_resources
            if configured_resources is not None
            else [
                "flownote://para/projects",
                "flownote://dashboard/summary",
            ]
        )

        # 연결된 클라이언트 목록: 향후 MCP 런타임에서 주입될 때까지 빈 리스트
        configured_clients = getattr(config, "active_clients", None)
        active_clients: list = (
            configured_clients if configured_clients is not None else []
        )

        return MCPStatusResponse(
            running=getattr(config, "server_running", False),
            active_clients=active_clients,
            tools_registered=registered_tools,
            resources_registered=registered_resources,
        )
    except Exception as e:
        log_agent_error(
            logger, f"Failed to get MCP status: {e}", e, include_traceback=True
        )
        raise HTTPException(
            status_code=500,
            detail="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from e


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
        log_agent_error(
            logger, f"Failed to get conflicts: {e}", e, include_traceback=True
        )
        raise HTTPException(
            status_code=500,
            detail="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from e


def _get_conflict(conflict_id: str) -> Optional[SyncConflict]:
    """저장된 충돌 로그에서 conflict_id로 충돌 정보 조회"""
    log_file = PathConfig.DATA_DIR / "sync_logs" / "detected_conflicts.jsonl"
    if not log_file.exists():
        return None
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
                if data.get("conflict_id") == conflict_id:
                    return SyncConflict(**data)
            except Exception:
                continue
    return None


@router.get("/conflicts/{conflict_id}/diff", response_model=ConflictDiffResponse)
async def get_conflict_diff(conflict_id: str):
    """
    충돌 파일의 Diff 데이터 반환
    """
    try:
        conflict = _get_conflict(conflict_id)
        if not conflict:
            raise HTTPException(status_code=404, detail="Conflict not found")

        local_path = Path(conflict.file_id)
        if local_path.exists():
            local_content = await asyncio.to_thread(
                local_path.read_text, encoding="utf-8"
            )
        else:
            local_content = ""

        # Setup Sync Service
        conn = ExternalToolConnection(
            tool_type=ExternalToolType.OBSIDIAN,
            config=ConnectionConfig(
                base_path=mcp_config.obsidian.vault_path,
                enabled=mcp_config.obsidian.enabled,
            ),
        )
        sync_service = ObsidianSyncService(conn)

        remote_content = await sync_service.pull_file(conflict.external_path)
        if remote_content is None:
            remote_content = ""

        diff_result = generate_diff(local_content, remote_content)

        return ConflictDiffResponse(
            conflict_id=conflict_id,
            local_content=local_content,
            remote_content=remote_content,
            diff=diff_result,
            file_type="markdown",
        )
    except HTTPException:
        raise
    except Exception as e:
        log_agent_error(
            logger, f"Failed to generate diff: {e}", e, include_traceback=True
        )
        raise HTTPException(
            status_code=500,
            detail="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from e


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    resolution_method: ResolutionStrategy,
):
    """
    충돌 해결

    Args:
        conflict_id: 충돌 ID
        resolution_method: 해결 방법 (keep_local, keep_remote, keep_both)

    Returns:
        dict: 해결 결과
    """
    try:
        conflict = _get_conflict(conflict_id)
        if not conflict:
            raise HTTPException(status_code=404, detail="Conflict not found")

        logger.info(
            f"Resolving conflict {conflict_id} with method: {resolution_method}"
        )

        # Map API enum to Domain model
        # MVP에서는 Rename(keep_both) 전략을 기본으로 사용
        domain_method = ResolutionMethod.AUTO_BY_CONTEXT
        if resolution_method != ResolutionStrategy.KEEP_BOTH:
            logger.warning(
                f"Resolution method {resolution_method} requested, but falling back to keep_both (rename) for MVP"
            )

        domain_strategy = DomainResolutionStrategy(
            method=domain_method,
            recommended_value=resolution_method.value,
            confidence=1.0,
            reasoning="User manually selected resolution from UI",
            conflict_id=conflict_id,
        )

        # Setup Services
        conn = ExternalToolConnection(
            tool_type=ExternalToolType.OBSIDIAN,
            config=ConnectionConfig(
                base_path=mcp_config.obsidian.vault_path,
                enabled=mcp_config.obsidian.enabled,
            ),
        )
        sync_service = ObsidianSyncService(conn)
        map_manager = SyncMapManager()
        conflict_service = ConflictResolutionService(sync_service, map_manager)

        # Resolve
        resolution = await conflict_service.resolve_conflict(conflict, domain_strategy)

        if resolution.status.value not in ("resolved", "resolved_with_rename"):
            if resolution.status.value == "failed":
                raise HTTPException(
                    status_code=500, detail="Failed to resolve conflict internally"
                )

        return {
            "conflict_id": conflict_id,
            "status": "resolved",
            "method": resolution_method,
            "timestamp": resolution.resolved_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        log_agent_error(
            logger, f"Failed to resolve conflict: {e}", e, include_traceback=True
        )
        raise HTTPException(
            status_code=500,
            detail="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from e

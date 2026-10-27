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
from backend.mcp.runtime_status import read_mcp_runtime_status
from backend.mcp.sync_map_manager import SyncMapManager, get_sync_map_manager
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
    """MCP 서버 상태 응답.

    Runtime and registrations are unavailable until the stdio server publishes
    its state through a channel shared with this API process.
    """

    running: Optional[bool] = None
    active_clients: Optional[List[str]] = None
    tools_registered: Optional[List[str]] = None
    resources_registered: Optional[List[str]] = None
    active_sessions: Optional[int] = None


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

        # 파일 개수 계산 (파일 I/O 에러 안전 방어)
        file_count = 0
        if connected and vault_path is not None:
            try:
                file_count = len(list(vault_path.rglob("*.md")))
            except OSError as exc:
                logger.warning(
                    "Failed to count markdown files in vault due to I/O error: %s",
                    exc,
                )
                file_count = 0

        # last_sync: SyncMapManager에서 Obsidian 도구 기준 최신 동기화 시각 실연동
        map_manager = get_sync_map_manager()
        last_sync = map_manager.get_latest_sync_time(
            tool_type=ExternalToolType.OBSIDIAN
        )

        return SyncStatusResponse(
            connected=connected,
            vault_path=str(vault_path) if vault_path else None,
            last_sync=last_sync,
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
        MCPStatusResponse: Redis heartbeat로 확인한 MCP stdio 프로세스와 세션 상태.
        Redis를 사용할 수 없는 경우 런타임 필드는 None으로 반환한다.
    """
    status = await read_mcp_runtime_status()
    return MCPStatusResponse(**status) if status is not None else MCPStatusResponse()


@router.get("/conflicts", response_model=List[ConflictLogResponse])
async def get_conflicts(
    limit: int = 50,
    status: Optional[str] = None,
):
    """
    충돌 이력 조회

    `sync_service.py`의 `_handle_conflict()`가 기록하는
    `detected_conflicts.jsonl` 파일을 읽어 실제 충돌 이력을 반환합니다.

    Args:
        limit: 조회할 최대 개수 (기본값 50, 최신순 정렬)
        status: 필터링할 상태 (예: "pending", "resolved"). 미지정 시 전체 반환.

    Returns:
        List[ConflictLogResponse]: 충돌 로그 목록 (최신 발생 순)
    """
    log_file = PathConfig.DATA_DIR / "sync_logs" / "detected_conflicts.jsonl"

    if not log_file.exists():
        logger.debug(
            "Conflict log file not found; returning empty list. path_exists=False"
        )
        return []

    conflicts: List[ConflictLogResponse] = []
    parse_error_count = 0

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        parse_error_count += 1
                        continue

                    # detected_at → timestamp 매핑 (ISO 8601 형식 안전 파싱)
                    detected_at_raw = data.get("detected_at")
                    try:
                        timestamp = (
                            datetime.fromisoformat(detected_at_raw)
                            if detected_at_raw
                            else datetime.now()
                        )
                    except (ValueError, TypeError):
                        timestamp = datetime.now()

                    # JSONL 레코드에 status 필드가 없는 경우 "pending"으로 기본 처리
                    # (detected_conflicts.jsonl은 감지 시점에만 기록되며,
                    #  해결 이력은 conflict_resolution.jsonl에 별도 저장됨)
                    record_status = data.get("status", "pending")

                    conflicts.append(
                        ConflictLogResponse(
                            conflict_id=data.get("conflict_id", ""),
                            timestamp=timestamp,
                            file_path=data.get("external_path", ""),
                            conflict_type=data.get("conflict_type", ""),
                            local_hash=data.get("local_hash", ""),
                            remote_hash=data.get("remote_hash", ""),
                            status=record_status,
                            resolution_method=data.get("resolution_method"),
                            notes=data.get("notes"),
                        )
                    )
                except (json.JSONDecodeError, KeyError, TypeError):
                    parse_error_count += 1
                    continue

        if parse_error_count > 0:
            logger.warning(
                "Conflict log parsing: %d line(s) skipped due to invalid format.",
                parse_error_count,
            )

    except OSError as exc:
        log_agent_error(logger, "Failed to read conflict log file", exc)
        raise HTTPException(
            status_code=500,
            detail="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from exc

    # 최신순 정렬 (detected_at 기준 내림차순)
    conflicts.sort(key=lambda c: c.timestamp, reverse=True)

    if status:
        conflicts = [c for c in conflicts if c.status == status]

    logger.debug(
        "Conflict log query: total=%d, status_filter=%s, returning=%d",
        len(conflicts),
        status or "all",
        min(len(conflicts), limit),
    )

    return conflicts[:limit]


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

    - 로컬/원격 파일이 없거나 읽기 불가 시 422를 반환하여
      유효한 빈 파일과 사용 불가 상태를 명확히 구분합니다.
    """
    try:
        conflict = _get_conflict(conflict_id)
        if not conflict:
            raise HTTPException(status_code=404, detail="Conflict not found")

        # 1. 로컬 파일 읽기 (존재하지 않으면 비교 불가 → 422)
        local_path = Path(conflict.file_id)
        if not local_path.exists():
            logger.warning(
                "Local file unavailable for diff (conflict_id=%s)",
                conflict.conflict_id,
            )
            raise HTTPException(
                status_code=422,
                detail="로컬 파일을 찾을 수 없어 비교를 수행할 수 없습니다.",
            )
        try:
            local_content = await asyncio.to_thread(
                local_path.read_text, encoding="utf-8"
            )
        except (OSError, UnicodeDecodeError) as read_err:
            logger.warning(
                "Failed to read local file for diff (conflict_id=%s)",
                conflict.conflict_id,
                extra={"error": type(read_err).__name__},
            )
            raise HTTPException(
                status_code=422,
                detail="로컬 파일을 읽을 수 없어 비교를 수행할 수 없습니다.",
            ) from read_err

        # 2. 원격 파일 읽기 (None = 파일 없음 또는 읽기 오류 → 422)
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
            logger.warning(
                "Remote file unavailable for diff (conflict_id=%s)",
                conflict.conflict_id,
            )
            raise HTTPException(
                status_code=422,
                detail="원격 파일을 읽을 수 없어 비교를 수행할 수 없습니다.",
            )

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

# backend/models/external_sync.py

"""
External Sync Models
외부 도구(Obsidian, Notion 등)와의 연결 및 동기화 상태를 관리하는 모델 정의
"""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class SyncStatus(str, Enum):
    """동기화 상태 열거형"""

    IDLE = "idle"
    SYNCING = "syncing"
    FAILED = "failed"
    COMPLETED = "completed"
    CONFLICT = "conflict"


class ExternalToolType(str, Enum):
    """지원하는 외부 도구 유형"""

    OBSIDIAN = "obsidian"
    NOTION = "notion"
    GDRIVE = "gdrive"


class ConnectionConfig(BaseModel):
    """연결 설정 (도구별 상이)"""

    base_path: Optional[str] = None  # for Obsidian (Vault Path)
    api_key: Optional[str] = None  # for Notion
    sync_interval: int = 300  # seconds
    enabled: bool = True


class ExternalToolConnection(BaseModel):
    """외부 도구 연결 상태"""

    tool_type: ExternalToolType
    config: ConnectionConfig
    last_synced_at: Optional[datetime] = None
    sync_status: SyncStatus = SyncStatus.IDLE
    error_message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "tool_type": "obsidian",
                "config": {"base_path": "/Users/jay/Documents/Vault", "enabled": True},
                "sync_status": "idle",
            }
        }


class ExternalFileMapping(BaseModel):
    """내부 파일과 외부 파일 간의 매핑 정보"""

    internal_file_id: str  # FlowNote ID
    external_path: str  # Obsidian Absolute Path or Notion Page ID
    tool_type: ExternalToolType
    last_synced_hash: Optional[str] = None  # 변경 감지용 해시
    last_synced_at: datetime = Field(default_factory=datetime.now)


class ExternalSyncLog(BaseModel):
    """동기화 활동 로그"""

    id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    tool_type: ExternalToolType
    action: str  # "pull", "push", "conflict_resolve"
    file_path: Optional[str] = None
    status: SyncStatus
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

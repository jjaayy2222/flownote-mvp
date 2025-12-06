# backend/models/conflict.py

"""
충돌 감지 및 해결 관련 Pydantic 모델

이 파일은 메타데이터 충돌 감지 및 해결을 위한 모델을 통합합니다:
- Enums: ConflictType, ResolutionMethod, ResolutionStatus
- Core Models: ConflictDetail, ConflictRecord, ResolutionStrategy, ConflictResolution
- Report Models: ConflictReport
- API Models: DetectConflictRequest, ResolveConflictRequest, etc.
"""

from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4
from .external_sync import ExternalToolType


# ==========================================
# Enums
# ==========================================


class ConflictType(str, Enum):
    """충돌 유형"""

    CATEGORY_CONFLICT = "category_conflict"
    KEYWORD_CONFLICT = "keyword_conflict"
    METADATA_CONFLICT = "metadata_conflict"
    PARA_CLASS_CONFLICT = "para_class"
    TIMESTAMP_CONFLICT = "timestamp"


class ResolutionMethod(str, Enum):
    """해결 방법"""

    AUTO_BY_CONFIDENCE = "auto_by_confidence"
    AUTO_BY_CONTEXT = "auto_by_context"
    MANUAL_OVERRIDE = "manual_override"
    VOTING = "voting"
    HYBRID = "hybrid"


class ResolutionStatus(str, Enum):
    """해결 상태"""

    PENDING = "pending"
    PENDING_REVIEW = "pending_review"
    RESOLVED = "resolved"
    FAILED = "failed"


# ==========================================
# Core Models
# ==========================================


class ConflictDetail(BaseModel):
    """
    충돌 상세 정보

    충돌이 발생한 필드와 값들을 저장
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "field": "category",
                "current_value": "Projects",
                "suggested_value": "Areas",
                "confidence": 0.85,
            }
        }
    )

    field: str = Field(..., description="충돌 필드명")
    current_value: Any = Field(..., description="현재 값")
    suggested_value: Any = Field(..., description="제안 값")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="신뢰도")


class ConflictRecord(BaseModel):
    """
    충돌 기록

    개별 충돌 사례를 기록
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conflict_id": "conflict_abc123",
                "type": "keyword_conflict",
                "description": "유사 키워드: 'python' vs 'py'",
                "severity": 0.8,
                "auto_resolvable": True,
                "created_at": "2025-11-17T12:00:00",
            }
        }
    )

    conflict_id: str = Field(
        default_factory=lambda: f"conflict_{uuid4().hex[:8]}", description="충돌 ID"
    )
    type: ConflictType = Field(..., description="충돌 유형")
    description: str = Field(..., description="충돌 설명")
    severity: float = Field(..., ge=0.0, le=1.0, description="심각도")
    auto_resolvable: bool = Field(default=True, description="자동 해결 가능 여부")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 시각")


class ResolutionStrategy(BaseModel):
    """
    해결 전략

    충돌 해결 방법 및 설정
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "method": "auto_by_confidence",
                "recommended_value": "Projects",
                "confidence": 0.92,
                "reasoning": "신뢰도가 threshold 이상",
                "conflict_id": "conflict_abc123",
            }
        }
    )

    method: ResolutionMethod = Field(..., description="해결 방법")
    recommended_value: Any = Field(..., description="권장 값")
    confidence: float = Field(..., ge=0.0, le=1.0, description="신뢰도")
    reasoning: str = Field(default="", description="해결 근거")
    conflict_id: str = Field(..., description="충돌 ID")


class ConflictResolution(BaseModel):
    """
    충돌 해결 결과

    충돌이 어떻게 해결되었는지 기록
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conflict_id": "conflict_abc123",
                "status": "resolved",
                "strategy": {
                    "method": "auto_by_confidence",
                    "recommended_value": "Projects",
                },
                "resolved_by": "system",
                "resolved_at": "2025-11-17T12:00:00",
                "notes": "자동 해결 완료",
            }
        }
    )

    conflict_id: str = Field(..., description="충돌 ID")
    status: ResolutionStatus = Field(..., description="해결 상태")
    strategy: Dict[str, Any] = Field(..., description="사용된 전략")
    resolved_by: str = Field(..., description="해결자 (system/user)")
    resolved_at: datetime = Field(default_factory=datetime.now, description="해결 시각")
    notes: str = Field(default="", description="비고")


# ==========================================
# Report Models
# ==========================================


class ConflictReport(BaseModel):
    """
    충돌 보고서

    전체 충돌 감지 및 해결 결과 요약
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_conflicts": 10,
                "detected_conflicts": [],
                "resolutions": [],
                "auto_resolved_count": 7,
                "manual_review_needed": 3,
                "resolution_rate": 0.7,
                "status": "completed",
                "summary": "10개 중 7개 자동 해결",
            }
        }
    )

    total_conflicts: int = Field(..., description="총 충돌 수")
    detected_conflicts: List[ConflictRecord] = Field(
        default_factory=list, description="감지된 충돌들"
    )
    resolutions: List[ConflictResolution] = Field(
        default_factory=list, description="해결 결과들"
    )
    auto_resolved_count: int = Field(default=0, description="자동 해결 수")
    manual_review_needed: int = Field(default=0, description="수동 검토 필요 수")
    resolution_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="해결률")
    status: str = Field(default="pending", description="전체 상태")
    summary: str = Field(default="", description="요약")


# ==========================================
# API Request/Response Models
# ==========================================


class DetectConflictRequest(BaseModel):
    """
    충돌 감지 요청

    분류 결과 간 충돌 감지를 요청
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "file_123",
                "current_classification": {"category": "Projects", "confidence": 0.85},
                "new_classification": {"category": "Areas", "confidence": 0.82},
            }
        }
    )

    file_id: str = Field(..., description="파일 ID")
    current_classification: Dict[str, Any] = Field(..., description="현재 분류")
    new_classification: Dict[str, Any] = Field(..., description="새 분류")


class ResolveConflictRequest(BaseModel):
    """
    충돌 해결 요청

    감지된 충돌을 해결하기 위한 요청
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conflict_id": "conflict_abc123",
                "strategy": {"method": "manual_override", "confidence_threshold": 0.8},
                "manual_value": "Projects",
            }
        }
    )

    conflict_id: str = Field(..., description="충돌 ID")
    strategy: ResolutionStrategy = Field(..., description="해결 전략")
    manual_value: Optional[Any] = Field(None, description="수동 선택 값")


class ConflictDetectResponse(BaseModel):
    """
    충돌 감지 응답

    감지된 충돌 정보 반환
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"conflicts": [], "has_conflicts": True, "total_count": 2}
        }
    )

    conflicts: List[ConflictRecord] = Field(
        default_factory=list, description="충돌 목록"
    )
    has_conflicts: bool = Field(..., description="충돌 존재 여부")
    total_count: int = Field(default=0, description="총 충돌 수")


class ConflictResolveResponse(BaseModel):
    """
    충돌 해결 응답

    해결 결과 반환
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resolution": {"conflict_id": "conflict_abc123", "status": "resolved"},
                "success": True,
            }
        }
    )

    resolution: ConflictResolution = Field(..., description="해결 결과")
    success: bool = Field(..., description="성공 여부")


__all__ = [
    # Enums
    "ConflictType",
    "ResolutionMethod",
    "ResolutionStatus",
    # Core Models
    "ConflictDetail",
    "ConflictRecord",
    "ResolutionStrategy",
    "ConflictResolution",
    "ConflictReport",
    # API Models
    "DetectConflictRequest",
    "ResolveConflictRequest",
    "ConflictDetectResponse",
    "ConflictResolveResponse",
    "ConflictResolveResponse",
    # Sync Conflict Models (Phase 3)
    "SyncConflict",
    "ConflictResolutionLog",
]


# ==========================================
# Sync Conflict Models (Phase 3)
# ==========================================


class SyncConflict(BaseModel):
    """
    동기화 충돌 정보 (Phase 3)

    로컬(FlowNote)과 원격(External Tool) 간의 데이터 불일치 상태를 정의
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conflict_id": "sync_conf_123",
                "file_id": "doc_abc",
                "external_path": "/Vault/Notes/doc.md",
                "tool_type": "obsidian",
                "conflict_type": "content_mismatch",
                "local_hash": "a1b2c3d4",
                "remote_hash": "e5f6g7h8",
                "status": "pending_review",
            }
        }
    )

    conflict_id: str = Field(
        default_factory=lambda: f"sync_conf_{uuid4().hex[:8]}",
        description="동기화 충돌 ID",
    )
    file_id: str = Field(..., description="내부 파일 ID")
    external_path: str = Field(..., description="외부 파일 경로")
    tool_type: ExternalToolType = Field(..., description="외부 도구 유형")
    conflict_type: str = Field(..., description="충돌 유형 (content_mismatch 등)")
    local_hash: Optional[str] = Field(None, description="로컬 파일 해시")
    remote_hash: Optional[str] = Field(None, description="원격 파일 해시")
    detected_at: datetime = Field(default_factory=datetime.now, description="감지 시각")
    status: ResolutionStatus = Field(
        default=ResolutionStatus.PENDING, description="해결 상태"
    )


class ConflictResolutionLog(BaseModel):
    """
    충돌 해결 로그 (Phase 3)
    """

    resolution_id: str = Field(
        default_factory=lambda: f"res_{uuid4().hex[:8]}", description="해결 로그 ID"
    )
    conflict_id: str = Field(..., description="관련 충돌 ID")
    strategy: ResolutionStrategy = Field(..., description="적용된 해결 전략")
    final_content_hash: Optional[str] = Field(None, description="최종 콘텐츠 해시")
    resolved_at: datetime = Field(default_factory=datetime.now, description="해결 시각")

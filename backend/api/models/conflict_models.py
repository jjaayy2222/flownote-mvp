# backend/api/models/conflict_models.py - 마이그레이션

"""
Conflict Detection & Resolution Models

    메타데이터 충돌 감지 및 해결을 위한 Pydantic 모델 정의
    - ConflictType: 충돌 유형 (category, keyword, timestamp)
    - ConflictRecord: 개별 충돌 기록
    - ResolutionStrategy: 해결 전략
    - ConflictReport: 최종 충돌 보고서
"""

from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4


# ==========================================
# Enums
# ==========================================
class ConflictType(str, Enum):
    """충돌 유형"""
    CATEGORY = "category"
    PARA_CLASS = "para_class"
    METADATA = "metadata"

class ResolutionMethod(str, Enum):
    """해결 방법"""
    AUTO = "auto"
    MANUAL = "manual"
    VOTING = "voting"

class ResolutionStatus(str, Enum):
    """해결 상태"""
    PENDING = "pending"
    RESOLVED = "resolved"
    FAILED = "failed"

# ==========================================
# Core Models
# ==========================================
class ConflictDetail(BaseModel):
    """충돌 상세 정보"""
    field: str
    current_value: Any
    suggested_value: Any
    confidence: Optional[float] = None

class ConflictRecord(BaseModel):
    """충돌 기록"""
    conflict_id: str
    file_id: str
    conflict_type: ConflictType
    details: ConflictDetail
    created_at: datetime = Field(default_factory=datetime.now)
    status: ResolutionStatus = ResolutionStatus.PENDING

class ResolutionStrategy(BaseModel):
    """해결 전략"""
    method: ResolutionMethod
    confidence_threshold: float = 0.7
    auto_resolve: bool = True

class ConflictResolution(BaseModel):
    """충돌 해결 결과"""
    conflict_id: str
    resolved_value: Any
    method: ResolutionMethod
    confidence: float
    resolved_at: datetime = Field(default_factory=datetime.now)

# ==========================================
# Report Models
# ==========================================
class ConflictReport(BaseModel):
    """충돌 리포트"""
    total_conflicts: int
    resolved_conflicts: int
    pending_conflicts: int
    conflicts_by_type: Dict[ConflictType, int]
    resolution_methods: Dict[ResolutionMethod, int]

# ==========================================
# API Request/Response Models
# ==========================================
class DetectConflictRequest(BaseModel):
    """충돌 감지 요청"""
    file_id: str
    current_classification: Dict[str, Any]
    new_classification: Dict[str, Any]

class ResolveConflictRequest(BaseModel):
    """충돌 해결 요청"""
    conflict_id: str
    strategy: ResolutionStrategy
    manual_value: Optional[Any] = None

class ConflictDetectResponse(BaseModel):
    """충돌 감지 응답"""
    conflicts: List[ConflictRecord]
    has_conflicts: bool

class ConflictResolveResponse(BaseModel):
    """충돌 해결 응답"""
    resolution: ConflictResolution
    success: bool


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
]

# backend/api/models/__init__.py - 마이그레이션 

"""
API Models Package

DEPRECATED: Conflict 모델들이 backend.models.conflict로 이동되었습니다.
"""


# Classification models
from backend.models.classification import (
    ClassifyRequest,
    ClassifyResponse,
    FileMetadataInput,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    SaveClassificationRequest,
    SearchRequest,
)

# Conflict models (re-export from backend.models)
from backend.models.conflict import (
    ConflictType,
    ResolutionMethod,
    ResolutionStatus,
    ConflictDetail,
    ConflictRecord,
    ResolutionStrategy,
    ConflictResolution,
    ConflictReport,
    DetectConflictRequest,
    ResolveConflictRequest,
    ConflictDetectResponse,
    ConflictResolveResponse,
)

__all__ = [
    # Classification
    "ClassifyRequest",
    "ClassifyResponse",
    "FileMetadataInput",
    "ClassifyBatchRequest",
    "ClassifyBatchResponse",
    "SaveClassificationRequest",
    "SearchRequest",
    
    # Conflict (re-export)
    "ConflictType",
    "ResolutionMethod",
    "ResolutionStatus",
    "ConflictDetail",
    "ConflictRecord",
    "ResolutionStrategy",
    "ConflictResolution",
    "ConflictReport",
    "DetectConflictRequest",
    "ResolveConflictRequest",
    "ConflictDetectResponse",
    "ConflictResolveResponse",
]

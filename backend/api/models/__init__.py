# backend/api/models/__init__.py - 마이그레이션 

"""
API Models Package
"""

# ==========================================
# 1. Models import (올바른 경로!)
# ==========================================
from backend.models.classification import (
    # Classification models
    ClassifyRequest,
    ClassifyResponse,
    FileMetadataInput,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    SaveClassificationRequest,
    SearchRequest,
)

# ==========================================
# 2. Conflict models import (올바른 경로!)
# ==========================================
from .conflict_models import (
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
    # Conflict
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

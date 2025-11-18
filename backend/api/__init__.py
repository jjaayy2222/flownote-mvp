# backend/api/__init__.py - 마이그레이션

"""
API Models Package
"""

# Models import (backend.models에서 직접)
from backend.models import (
    # Classification models
    ClassifyRequest,
    ClassificationRequest,
    MetadataClassifyRequest,
    HybridClassifyRequest,
    ParallelClassifyRequest,
    ClassifyResponse,
    ClassificationResponse,
    FileMetadataInput,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    SaveClassificationRequest,
    SearchRequest,
)

# Conflict models (backend.models에서 직접)
from backend.models import (
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
    "ClassificationRequest",
    "MetadataClassifyRequest",
    "HybridClassifyRequest",
    "ParallelClassifyRequest",
    "ClassifyResponse",
    "ClassificationResponse",
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

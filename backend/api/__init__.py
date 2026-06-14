# backend/api/__init__.py - 마이그레이션

"""
API Models Package
"""

# Conflict models (backend.models에서 직접)
# Models import (backend.models에서 직접)
from backend.models import (
    ClassificationRequest,  # Classification models
    ClassificationResponse,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    ClassifyRequest,
    ClassifyResponse,
    ConflictDetail,
    ConflictDetectResponse,
    ConflictRecord,
    ConflictReport,
    ConflictResolution,
    ConflictResolveResponse,
    ConflictType,
    DetectConflictRequest,
    FileMetadataInput,
    HybridClassifyRequest,
    MetadataClassifyRequest,
    ParallelClassifyRequest,
    ResolutionMethod,
    ResolutionStatus,
    ResolutionStrategy,
    ResolveConflictRequest,
    SaveClassificationRequest,
    SearchRequest,
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

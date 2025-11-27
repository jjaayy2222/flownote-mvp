# backend/api/__init__.py - 마이그레이션

"""
API Models Package
"""

<<<<<<< HEAD
"""
backend/api/__init__.py
"""

# ==========================================
# 1. Models import
# ==========================================
from backend.models import (
    # Classification models
    ClassifyRequest,
    ClassificationRequest,
    MetadataClassifyRequest,
    HybridClassifyRequest,
    ParallelClassifyRequest,
    ClassifyResponse,
    ClassificationResponse,
    #FileMetadata,
    FileMetadataInput,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    SaveClassificationRequest,
    SearchRequest,
)


# ==========================================
# 2. Conflict models import (올바른 경로!)
# ==========================================
from .models.conflict_models import (  
=======
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
>>>>>>> origin/refactor/v4-backend-cleanup
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

<<<<<<< HEAD
=======

>>>>>>> origin/refactor/v4-backend-cleanup
__all__ = [
    # Classification
    "ClassifyRequest",
    "ClassificationRequest",
    "MetadataClassifyRequest",
    "HybridClassifyRequest",
    "ParallelClassifyRequest",
    "ClassifyResponse",
    "ClassificationResponse",
<<<<<<< HEAD
    #"FileMetadata",
=======
>>>>>>> origin/refactor/v4-backend-cleanup
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

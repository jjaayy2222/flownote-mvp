# backend/api/models/__init__.py - 마이그레이션 

"""
API Models Package
<<<<<<< HEAD
"""

# ==========================================
# 1. Models import (올바른 경로!)
# ==========================================
from backend.models.classification import (
    # Classification models
=======

DEPRECATED: Conflict 모델들이 backend.models.conflict로 이동되었습니다.
"""


# Classification models
from backend.models.classification import (
>>>>>>> origin/refactor/v4-backend-cleanup
    ClassifyRequest,
    ClassifyResponse,
    FileMetadataInput,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    SaveClassificationRequest,
    SearchRequest,
)

<<<<<<< HEAD
# ==========================================
# 2. Conflict models import (올바른 경로!)
# ==========================================
from .conflict_models import (
=======
# Conflict models (re-export from backend.models)
from backend.models.conflict import (
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

__all__ = [
    # Classification
    "ClassifyRequest",
    "ClassifyResponse",
    "FileMetadataInput",
    "ClassifyBatchRequest",
    "ClassifyBatchResponse",
    "SaveClassificationRequest",
    "SearchRequest",
<<<<<<< HEAD
    # Conflict
=======
    
    # Conflict (re-export)
>>>>>>> origin/refactor/v4-backend-cleanup
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

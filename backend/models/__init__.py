# backend/models/__init__.py

"""
통합 모델 패키지 (backend.models)

<<<<<<< HEAD
- 분류 관련 Pydantic 모델만 re-export
- 다른 패키지(backend.api.* 등)는 여기서 import 하지 않음
"""

from .classification import (
    # 요청 모델
    ClassifyRequest,
    ClassificationRequest,
    MetadataClassifyRequest,
    HybridClassifyRequest,
    ParallelClassifyRequest,

    # 응답 모델
    ClassifyResponse,
    ClassificationResponse,
    ClassifyBatchRequest,
    ClassifyBatchResponse,

    # 파일 메타데이터 (Pydantic 버전)
    FileMetadata,
    FileMetadataInput,

    # API 전용 요청 모델
=======
    - Classification: 분류 관련 모델
    - User: 사용자 관련 모델
    - Common: 공통 모델
    - Conflict: 충돌 감지 및 해결 모델 (NEW!)

    - 분류 관련 Pydantic 모델만 re-export
    - 다른 패키지(backend.api.* 등)는 여기서 import 하지 않음
"""

# Classification (Phase 2.1에서 추가됨)
from .classification import (
    ClassifyRequest,
    ClassifyResponse,
    ClassificationRequest,
    ClassificationResponse,
    MetadataClassifyRequest,
    HybridClassifyRequest,
    ParallelClassifyRequest,
    FileMetadata as ClassificationFileMetadata,  # 이름 충돌 방지
    FileMetadataInput,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    SaveClassificationRequest as ClassificationSaveRequest,  # 이름 충돌 방지
    SearchRequest as ClassificationSearchRequest,  # 이름 충돌 방지
    PARAClassificationOutput,
)

# User (Phase 2.2에서 추가됨)
from .user import (
    Step1Input,
    Step2Input,
    OnboardingStatus,
    UserProfile,
    UserContext,
)

# Common (Phase 2.2에서 추가됨)
from .common import (
    ErrorResponse,
    SuccessResponse,
    HealthCheckResponse,
    FileMetadata,
    MetadataResponse,
>>>>>>> origin/refactor/v4-backend-cleanup
    SaveClassificationRequest,
    SearchRequest,
)

<<<<<<< HEAD

__all__ = [
    # 요청
    "ClassifyRequest",
    "ClassificationRequest",
    "MetadataClassifyRequest",
    "HybridClassifyRequest",
    "ParallelClassifyRequest",

    # 응답
    "ClassifyResponse",
    "ClassificationResponse",
    "ClassifyBatchRequest",
    "ClassifyBatchResponse",

    # 메타데이터
    "FileMetadata",
    "FileMetadataInput",

    # API 전용
    "SaveClassificationRequest",
    "SearchRequest",
=======
# Conflict (Phase 2.3 - NEW!)
from .conflict import (
    # Enums
    ConflictType,
    ResolutionMethod,
    ResolutionStatus,
    # Core Models
    ConflictDetail,
    ConflictRecord,
    ResolutionStrategy,
    ConflictResolution,
    ConflictReport,
    # API Models
    DetectConflictRequest,
    ResolveConflictRequest,
    ConflictDetectResponse,
    ConflictResolveResponse,
)




__all__ = [
    # Classification
    "ClassifyRequest",
    "ClassifyResponse",
    "ClassificationRequest",
    "ClassificationResponse",
    "MetadataClassifyRequest",
    "HybridClassifyRequest",
    "ParallelClassifyRequest",
    "ClassificationFileMetadata",
    "FileMetadataInput",
    "ClassifyBatchRequest",
    "ClassifyBatchResponse",
    "ClassificationSaveRequest",
    "ClassificationSearchRequest",
    "PARAClassificationOutput",
    
    # User
    "Step1Input",
    "Step2Input",
    "OnboardingStatus",
    "UserProfile",
    "UserContext",
    
    # Common
    "ErrorResponse",
    "SuccessResponse",
    "HealthCheckResponse",
    "FileMetadata",
    "MetadataResponse",
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
>>>>>>> origin/refactor/v4-backend-cleanup
]

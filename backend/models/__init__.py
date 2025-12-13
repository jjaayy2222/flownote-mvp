# backend/models/__init__.py

"""
통합 모델 패키지 (backend.models)

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
    SaveClassificationRequest,
    SearchRequest,
)

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

# External Sync (Phase 3 - NEW!)
from .external_sync import (
    ExternalToolConnection,
    ExternalFileMapping,
    ExternalSyncLog,
    SyncStatus,
    ExternalToolType,
)

# Automation (Phase 4 - NEW!)
from .automation import (
    AutomationTaskType,
    AutomationStatus,
    AutomationRule,
    AutomationLog,
    ReclassificationRecord,
    ArchivingRecord,
)

# Reporting (Phase 4)
from .report import (
    ReportType,
    ReportMetric,
    Report,
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
    # External Sync (Phase 3 - NEW!)
    "ExternalToolConnection",
    "ExternalFileMapping",
    "ExternalSyncLog",
    "SyncStatus",
    "ExternalToolType",
    # Automation (Phase 4 - NEW!)
    "AutomationTaskType",
    "AutomationStatus",
    "AutomationRule",
    "AutomationLog",
    "ReclassificationRecord",
    "ReclassificationRecord",
    "ArchivingRecord",
    # Reporting (Phase 4)
    "ReportType",
    "ReportMetric",
    "Report",
]

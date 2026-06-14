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

# Automation (Phase 4 - NEW!)
from .automation import (
    ArchivingRecord,
    AutomationLog,
    AutomationRule,
    AutomationStatus,
    AutomationTaskType,
    ReclassificationRecord,
)

# Classification (Phase 2.1에서 추가됨)
from .classification import (
    ClassificationRequest,
    ClassificationResponse,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    ClassifyRequest,
    ClassifyResponse,
)
from .classification import FileMetadata as ClassificationFileMetadata  # 이름 충돌 방지
from .classification import (
    FileMetadataInput,
    HybridClassifyRequest,
    MetadataClassifyRequest,
    PARAClassificationOutput,
    ParallelClassifyRequest,
)
from .classification import (
    SaveClassificationRequest as ClassificationSaveRequest,
)  # 이름 충돌 방지
from .classification import (
    SearchRequest as ClassificationSearchRequest,
)  # 이름 충돌 방지

# Common (Phase 2.2에서 추가됨)
from .common import (
    ErrorResponse,
    FileMetadata,
    HealthCheckResponse,
    MetadataResponse,
    SaveClassificationRequest,
    SearchRequest,
    SuccessResponse,
)

# Conflict (Phase 2.3 - NEW!)
from .conflict import (
    ConflictDetail,  # Enums; Core Models; API Models
    ConflictDetectResponse,
    ConflictRecord,
    ConflictReport,
    ConflictResolution,
    ConflictResolveResponse,
    ConflictType,
    DetectConflictRequest,
    ResolutionMethod,
    ResolutionStatus,
    ResolutionStrategy,
    ResolveConflictRequest,
)

# External Sync (Phase 3 - NEW!)
from .external_sync import (
    ExternalFileMapping,
    ExternalSyncLog,
    ExternalToolConnection,
    ExternalToolType,
    SyncStatus,
)

# Reporting (Phase 4)
from .report import Report, ReportMetric, ReportType

# User (Phase 2.2에서 추가됨)
from .user import OnboardingStatus, Step1Input, Step2Input, UserContext, UserProfile

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
    "ArchivingRecord",
    # Reporting (Phase 4)
    "ReportType",
    "ReportMetric",
    "Report",
]

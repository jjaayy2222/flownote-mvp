# backend/api/models/__init__.py

"""
API Models Package
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

# Core Models - Classification
from backend.models.classification import (
    ClassifyRequest,
    ClassifyResponse,
    FileMetadata,
    FileMetadataInput,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    SaveClassificationRequest,
    SearchRequest,
)

# Core Models - Conflict
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

# ---------------------------------------------------------
# API Layer Specific Response Models (Merged from models.py)
# ---------------------------------------------------------


class BaseResponse(BaseModel):
    """기본 응답 모델 (다국어 메시지 포함)"""

    status: str
    message: str


class HealthCheckResponse(BaseResponse):
    """헬스체크 응답"""

    pass


class FileProcessingResponse(BaseResponse):
    """파일 처리 응답"""

    file: str


class SearchResponse(BaseResponse):
    """검색 응답"""

    query: str
    results: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class MetadataResponse(BaseResponse):
    """메타데이터 조회/업데이트 응답"""

    pass


__all__ = [
    # Classification (Core)
    "ClassifyRequest",
    "ClassifyResponse",
    "FileMetadata",
    "FileMetadataInput",
    "ClassifyBatchRequest",
    "ClassifyBatchResponse",
    "SaveClassificationRequest",
    "SearchRequest",
    # Conflict (Core)
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
    # API Responses
    "BaseResponse",
    "HealthCheckResponse",
    "FileProcessingResponse",
    "SearchResponse",
    "MetadataResponse",
]

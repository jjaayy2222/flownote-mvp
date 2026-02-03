# backend/api/models.py - 마이그레이션

"""
Classification models for API layer
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from backend.models import (
    ClassifyRequest,
    ClassifyResponse,
    FileMetadata,
    FileMetadataInput,
    ClassifyBatchResponse,
    SaveClassificationRequest,
    SearchRequest,
)


# Common i18n Response Models
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

    file_id: str
    metadata: Optional[Dict[str, Any]] = None


__all__ = [
    # Classification
    "ClassifyRequest",
    "ClassifyResponse",
    "FileMetadataInput",
    "ClassifyBatchRequest",
    "ClassifyBatchResponse",
    # File Management
    "FileMetadata",
    "SaveClassificationRequest",
    "SearchRequest",
    # i18n Response Models
    "BaseResponse",
    "HealthCheckResponse",
    "FileProcessingResponse",
    "SearchResponse",
    "MetadataResponse",
]

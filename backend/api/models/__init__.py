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


# ---------------------------------------------------------
# Hybrid Search API Models (Step 6: RAG API Integration)
# ---------------------------------------------------------

PARA_CATEGORIES = ["Projects", "Areas", "Resources", "Archives"]


class HybridSearchRequest(BaseModel):
    """하이브리드 검색 요청 스키마

    Attributes:
        query: 검색 질의 문자열
        k: 반환할 최종 결과 수 (1 이상)
        alpha: Dense(FAISS) 검색 가중치 [0.0, 1.0] (기본값 0.5 = 균형)
        category: PARA 카테고리 필터 (선택). 단일 카테고리 문자열.
        metadata_filter: 추가 메타데이터 필터 조건 (카테고리 외 필드 필터링)
    """

    query: str = Field(..., min_length=1, description="검색 질의")
    k: int = Field(default=5, ge=1, le=50, description="반환할 결과 수 (1~50)")
    alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Dense 검색 가중치 (0.0=BM25 전용, 1.0=FAISS 전용, 0.5=균형)",
    )
    category: Optional[str] = Field(
        default=None,
        description=f"PARA 카테고리 필터. 허용값: {PARA_CATEGORIES}",
    )
    metadata_filter: Optional[Dict[str, Any]] = Field(
        default=None,
        description='추가 메타데이터 필터 (예: {"source": "my_notes.md"})',
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "프로젝트 일정 관리",
                    "k": 5,
                    "alpha": 0.5,
                    "category": "Projects",
                },
                {
                    "query": "Python 비동기 처리",
                    "k": 3,
                    "alpha": 0.7,
                    "category": None,
                    "metadata_filter": {"source": "dev_notes.md"},
                },
            ]
        }
    }


class SearchResultItem(BaseModel):
    """개별 검색 결과 항목"""

    content: str = Field(..., description="문서 내용")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="문서 메타데이터")
    score: float = Field(..., description="RRF 병합 점수")


class HybridSearchResponse(BaseModel):
    """하이브리드 검색 응답 스키마"""

    status: str = Field(..., description="응답 상태 ('success' 또는 'error')")
    query: str = Field(..., description="원본 검색 질의")
    results: List[SearchResultItem] = Field(
        default_factory=list, description="RRF 점수 기준 정렬된 검색 결과"
    )
    count: int = Field(..., description="반환된 결과 수")
    alpha: float = Field(..., description="사용된 Dense 검색 가중치")
    applied_filter: Optional[Dict[str, Any]] = Field(
        default=None, description="실제 적용된 메타데이터 필터"
    )


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
    # Hybrid Search (Step 6)
    "PARA_CATEGORIES",
    "HybridSearchRequest",
    "SearchResultItem",
    "HybridSearchResponse",
]

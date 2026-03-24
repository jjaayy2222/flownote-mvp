# backend/api/models/__init__.py

"""
API Models Package
"""

from enum import Enum
from functools import lru_cache
from typing import cast, Iterable, List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field  # type: ignore[import]

# Core Models - Classification
from backend.models.classification import (  # type: ignore[import]

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
from backend.models.conflict import (  # type: ignore[import]

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
# Common Types & Aliases
# ---------------------------------------------------------

ApiStatus = Literal["success", "error"]
SuccessStatus = Literal["success"]  # API가 항상 성공 객체만 반환하는 명시적 응답 컨트랙트용
FeedbackRating = Literal["up", "down", "none"]

# OpenAPI/Swagger Field Descriptions
API_STATUS_DESC = "API 응답 상태 ('success' 또는 'error')"
SUCCESS_STATUS_DESC = "API 성공 응답 상태 ('success')"
FEEDBACK_RATING_DESC = "피드백 평가 값 ('up', 'down', 'none')"


# ---------------------------------------------------------
# API Layer Specific Response Models (Merged from models.py)
# ---------------------------------------------------------


class BaseResponse(BaseModel):
    """기본 응답 모델 (다국어 메시지 포함)"""

    status: ApiStatus = Field(..., description=API_STATUS_DESC)
    message: str = Field(..., description="응답 메시지")


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


class PARACategory(str, Enum):
    """PARA 방법론 카테고리 Enum.

    ``str`` 을 상속하므로 JSON 직렬화 시 문자열로 자동 변환되고,
    FastAPI/OpenAPI 스펙에 ``enum`` 배열로 노출되어 Swagger UI에서
    드롭다운 선택이 가능합니다.
    """

    PROJECTS = "Projects"
    AREAS = "Areas"
    RESOURCES = "Resources"
    ARCHIVES = "Archives"


# 하위 호환용 문자열 리스트 (기존 코드 참조 시 사용)
# [Pyre2 Workaround]: Enum 반복 시 cat.value가 속성(property)으로 잘못 추론되어 발생하는
# `list[property] is not assignable to list[str]` Type Error (False Positive)를 우회하기 위한 조치.
# (유사 이슈: https://github.com/facebook/pyre-check/issues/224). 
# list(PARACategory)에 명시적인 Iterable 캐스팅을 적용합니다.
PARA_CATEGORIES: List[str] = [str(cat.value) for cat in cast(Iterable[PARACategory], list(PARACategory))]


class HybridSearchRequest(BaseModel):
    """하이브리드 검색 요청 스키마

    Attributes:
        query: 검색 질의 문자열
        k: 반환할 최종 결과 수 (1~50)
        alpha: Dense(FAISS) 검색 가중치 [0.0, 1.0] (기본값 0.5 = 균형)
        category: PARA 카테고리 필터 (선택). OpenAPI 스펙에 enum으로 노출.
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
    category: Optional[PARACategory] = Field(
        default=None,
        description="PARA 카테고리 필터 (Projects / Areas / Resources / Archives)",
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
    """개별 검색 결과 항목.

    API 응답 규격으로서, 프론트엔드 React key로 활용되는 `id`가 필수이며
    백엔드 하이브리드 검색 레이어에서 보장하는 고유 식별자가 포함됩니다.
    """

    id: str = Field(..., description="문서 고유 식별자 (파일명-청크인덱스 등)")
    content: str = Field(..., description="문서 내용")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="문서 메타데이터"
    )
    score: float = Field(..., description="RRF 병합 점수")


class HybridSearchResponse(BaseModel):
    """하이브리드 검색 응답 스키마"""

    status: ApiStatus = Field(..., description=API_STATUS_DESC)
    query: str = Field(..., description="원본 검색 질의")
    results: List[SearchResultItem] = Field(
        default_factory=list, description="RRF 점수 기준 정렬된 검색 결과"
    )
    count: int = Field(..., description="반환된 결과 수")
    alpha: float = Field(..., description="사용된 Dense 검색 가중치")
    applied_filter: Optional[Dict[str, Any]] = Field(
        default=None, description="실제 적용된 메타데이터 필터"
    )


# ---------------------------------------------------------
# Chat Streaming API Models (Step 7: RAG API Integration)
# ---------------------------------------------------------


class ChatQueryRequest(BaseModel):
    """채팅 질의 요청 스키마"""

    query: str = Field(..., description="사용자 질의 텍스트")
    user_id: str = Field(..., description="사용자 ID (온보딩 및 세션 식별용)")
    session_id: Optional[str] = Field(
        default=None, description="세션 ID (대화 맥락 유지용)"
    )
    k: int = Field(
        default=5, ge=1, le=20, description="RAG 검색에 사용할 최대 컨텍스트(문서) 수"
    )
    alpha: float = Field(
        default=0.5, ge=0.0, le=1.0, description="하이브리드 검색 FAISS 가중치"
    )


class ChatMessage(BaseModel):
    """채팅 메시지 개별 항목 모델"""

    role: str = Field(..., description="메시지 발신자 역할 (user, assistant, system)")
    content: str = Field(..., description="메시지 내용")
    timestamp: Optional[str] = Field(None, description="ISO 형식의 타임스탬프")


class ChatHistoryResponse(BaseModel):
    """채팅 히스토리 응답 모델"""

    status: ApiStatus = Field(..., description=API_STATUS_DESC)
    session_id: str = Field(..., description="세션 ID")
    messages: List[ChatMessage] = Field(default_factory=list, description="대화 내역 리스트")


class ChatSessionMeta(BaseModel):
    """세션 메타데이터 모델"""

    session_id: str = Field(..., description="세션 ID")
    user_id: str = Field(..., description="사용자 ID")
    name: Optional[str] = Field(None, description="세션 이름 (선택)")
    created_at: str = Field(..., description="생성 시각 (ISO 형식)")
    last_active_at: str = Field(..., description="마지막 활성 시각 (ISO 형식)")
    preview: Optional[str] = Field(None, description="마지막 메시지 미리보기")


class SessionListResponse(BaseModel):
    """세션 목록 응답 모델"""

    status: ApiStatus = Field(..., description=API_STATUS_DESC)
    user_id: str = Field(..., description="사용자 ID")
    sessions: List[ChatSessionMeta] = Field(default_factory=list, description="세션 목록")
    count: int = Field(0, description="세션 수")


class RenameSessionRequest(BaseModel):
    """세션 이름 수정 요청 모델"""

    name: str = Field(..., min_length=1, max_length=100, description="새 세션 이름")


# ---------------------------------------------------------
# Feedback / Observability Models (Issue #777)
# ---------------------------------------------------------


class FeedbackRequest(BaseModel):
    """AI 응답 피드백(Thumbs) 요청 모델"""

    session_id: str = Field(..., description="현재 세션 ID")
    message_id: str = Field(..., description="피드백 대상 메시지 ID")
    rating: FeedbackRating = Field(..., description=FEEDBACK_RATING_DESC)
    feedback_text: Optional[str] = Field(
        None, 
        max_length=1000, 
        description="추가 코멘트 (선택사항, 최대 1000자)"
    )


class FeedbackResponse(BaseModel):
    """피드백 제출 응답 모델"""

    status: SuccessStatus = Field(..., description=SUCCESS_STATUS_DESC)
    message_id: str = Field(..., description="적용된 메시지 ID")
    rating: FeedbackRating = Field(..., description=FEEDBACK_RATING_DESC)


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
    "ApiStatus",
    "SuccessStatus",
    "FeedbackRating",
    "BaseResponse",
    "HealthCheckResponse",
    "FileProcessingResponse",
    "SearchResponse",
    "MetadataResponse",
    # Hybrid Search (Step 6)
    "PARACategory",
    "PARA_CATEGORIES",
    "HybridSearchRequest",
    "SearchResultItem",
    "HybridSearchResponse",
    # Chat (Step 7)
    "ChatQueryRequest",
    "ChatMessage",
    "ChatHistoryResponse",
    # Session Management (Issue #776)
    "ChatSessionMeta",
    "SessionListResponse",
    "RenameSessionRequest",
    # Observability (Issue #777)
    "FeedbackRequest",
    "FeedbackResponse",
]

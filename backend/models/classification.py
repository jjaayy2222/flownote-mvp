# backend/models/classification.py

"""
통합 분류 모델 (Pydantic V2)
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# ============================================
# Request Models
# ============================================

class ClassifyRequest(BaseModel):
    """텍스트 분류 요청"""
    # 필수
    text: str = Field(..., min_length=1, description="분류할 텍스트")
    
    # 사용자 식별
    user_id: Optional[str] = Field(None, description="사용자 ID")
    file_id: Optional[str] = Field(None, description="파일 ID")
    
    # 사용자 맥락 (프롬프트 대응)
    occupation: Optional[str] = Field(None, description="직업")
    areas: Optional[List[str]] = Field(default_factory=list, description="책임 영역")
    interests: Optional[List[str]] = Field(default_factory=list, description="관심사")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "프로젝트 완성하기",
                "user_id": "user123",
                "occupation": "개발자",
                "areas": ["백엔드", "AI"],
                "interests": ["머신러닝"]
            }
        }
    )

class ClassificationRequest(BaseModel):
    text: str
    filename: str = "unknown"
    user_id: Optional[str] = None

class MetadataClassifyRequest(BaseModel):
    metadata: Dict
    user_id: Optional[str] = None

class HybridClassifyRequest(BaseModel):
    text: str
    metadata: Dict
    user_id: Optional[str] = None

class ParallelClassifyRequest(BaseModel):
    text: str
    metadata: Dict
    filename: str = "unknown"
    user_id: Optional[str] = None


# ============================================
# Response Models
# ============================================

class ClassifyResponse(BaseModel):
    """분류 결과 (conflict_resolver 반환값 기반)"""
    
    # ========== 필수 결과 ==========
    category: str = Field(..., description="PARA 카테고리")
    confidence: float = Field(..., ge=0.0, le=1.0, description="신뢰도")
    
    # ========== 키워드 분류 ==========
    keyword_tags: List[str] = Field(default_factory=list, description="키워드 태그")
    reasoning: str = Field(default="", description="분류 근거")
    
    # ========== 스냅샷/메타데이터 ==========
    snapshot_id: Optional[str] = Field(None, description="스냅샷 ID")
    
    # ========== 충돌 관련 ==========
    conflict_detected: bool = Field(default=False, description="충돌 감지 여부")
    requires_review: bool = Field(default=False, description="리뷰 필요 여부")
    
    # ========== 사용자 맥락 ==========
    user_context_matched: bool = Field(default=False, description="컨텍스트 매칭 여부")
    user_areas: List[str] = Field(default_factory=list, description="사용자 영역")
    user_context: Dict[str, Any] = Field(default_factory=dict, description="사용자 컨텍스트")
    context_injected: bool = Field(default=False, description="컨텍스트 주입 여부")
    
    # ========== 로그 정보 (🔥 핵심!) ==========
    log_info: Dict[str, Any] = Field(
        default_factory=dict,
        description="로그 정보 (timestamp, processing_time, llm_calls)"
    )
    csv_log_result: Dict[str, Any] = Field(
        default_factory=dict,
        description="CSV 로그 결과 (saved, file_path, row_id, error)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "category": "Projects",
                "confidence": 0.9,
                "keyword_tags": ["업무", "프로젝트"],
                "reasoning": "프로젝트 관련 키워드 발견",
                "snapshot_id": "snap_20251115_001",
                "conflict_detected": False,
                "requires_review": False,
                "user_context_matched": True,
                "user_areas": ["백엔드"],
                "user_context": {"occupation": "개발자"},
                "context_injected": True,
                "log_info": {
                    "timestamp": "2025-11-15T11:38:00",
                    "processing_time_ms": 1234,
                    "llm_calls": 2
                },
                "csv_log_result": {
                    "saved": True,
                    "file_path": "classification_log.csv",
                    "row_id": 123
                }
            }
        }
    )

class ClassificationResponse(BaseModel):
    category: str
    confidence: float
    status: str = "success"



# ============================================
# 확장 모델 (나중에 사용)
# ============================================

class FileMetadata(BaseModel):
    file_id: str
    filename: str
    category: str
    para_class: str
    created_at: Optional[str] = None

class FileMetadataInput(BaseModel):
    """파일 메타데이터 입력 (파일 업로드용)"""
    filename: str = Field(..., description="파일명")
    file_size: int = Field(..., gt=0, description="파일 크기 (bytes)")
    user_id: Optional[str] = Field(None, description="사용자 ID")
    file_id: Optional[str] = Field(None, description="파일 ID")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filename": "project_plan.pdf",
                "file_size": 1024000,
                "user_id": "user_123"
            }
        }
    )


class ClassifyBatchRequest(BaseModel):
    """배치 분류 요청"""
    texts: List[str] = Field(..., description="텍스트 리스트")
    user_id: Optional[str] = None



class ClassifyBatchResponse(BaseModel):
    """배치 분류 응답"""
    results: List[ClassifyResponse] = Field(..., description="분류 결과 리스트")
    total: int = Field(..., description="총 개수")
    success_count: int = Field(..., description="성공 개수")
    fail_count: int = Field(default=0, description="실패 개수")


# ============================================
# API 전용 모델 (추가!)
# ============================================
class SaveClassificationRequest(BaseModel):
    """분류 결과 저장 요청"""
    file_id: str = Field(..., description="파일 ID")
    classification: Dict[str, Any] = Field(..., description="분류 결과")

class SearchRequest(BaseModel):
    """검색 요청"""
    query: str = Field(..., description="검색 쿼리")
    filters: Optional[Dict[str, Any]] = Field(None, description="필터")


<<<<<<< HEAD
=======
# ============================================
# LangChain 통합 모델
# ============================================

class PARAClassificationOutput(BaseModel):
    """
    PARA 분류 결과 스키마 (LangChain 통합)
    
    LangChain 기반 분류 시 사용하는 출력 형식
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "category": "Projects",
                "confidence": 0.92,
                "reasoning": "명확한 목표와 기한이 있음",
                "detected_cues": ["프로젝트", "MVP", "완성"]
            }
        }
    )
    
    category: str = Field(..., description="PARA 카테고리 (Projects/Areas/Resources/Archives)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="신뢰도 점수")
    reasoning: str = Field(..., description="분류 이유 (한국어)")
    detected_cues: List[str] = Field(default_factory=list, description="감지된 키워드 목록")



__all__ = [
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
]

>>>>>>> origin/refactor/v4-backend-cleanup

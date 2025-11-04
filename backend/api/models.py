# backend/routes/api_models.py

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# ============================================
# Request Models
# ============================================

class ClassifyRequest(BaseModel):
    """분류 요청"""
    text: str = Field(..., min_length=1, description="분류할 텍스트")
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "프로젝트 완성하기"
            }
        }


# ============================================
# Response Models (conflict_resolver 반환값 기반)
# ============================================

class ClassifyResponse(BaseModel):
    """분류 결과"""
    final_category: str = Field(..., description="최종 카테고리")
    para_category: str = Field(..., description="PARA 카테고리")
    keyword_tags: List[str] = Field(default_factory=list, description="키워드 태그")
    confidence: float = Field(..., ge=0.0, le=1.0, description="신뢰도")
    confidence_gap: float = Field(..., description="신뢰도 차이")
    conflict_detected: bool = Field(..., description="충돌 감지")
    resolution_method: str = Field(..., description="해결 방법")
    requires_review: bool = Field(..., description="사용자 검토 필요")
    
    class Config:
        json_schema_extra = {
            "example": {
                "final_category": "Projects",
                "para_category": "Projects",
                "keyword_tags": ["업무", "프로젝트"],
                "confidence": 0.9,
                "confidence_gap": 0.15,
                "conflict_detected": False,
                "resolution_method": "auto_by_confidence",
                "requires_review": False
            }
        }


class MetadataResponse(BaseModel):
    """메타데이터 조회"""
    file_id: str
    para_category: str
    keyword_tags: List[str]
    confidence_score: float
    conflict_flag: bool
    manual_override: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "abc123",
                "para_category": "Projects",
                "keyword_tags": ["업무", "프로젝트"],
                "confidence_score": 0.9,
                "conflict_flag": False,
                "manual_override": None,
                "created_at": "2025-11-04T11:45:00",
                "updated_at": "2025-11-04T11:45:00"
            }
        }


# ============================================
# Error Models
# ============================================

class ErrorResponse(BaseModel):
    """에러 응답"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)



"""test_result_1 - 간결 버전으로 테스트

    python -c "from backend.routes.api_models import ClassifyRequest, ClassifyResponse; print('✅ Success!')"
    
    ✅ Success!

"""

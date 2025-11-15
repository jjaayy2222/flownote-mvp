# backend/routes/api_models.py

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# 모델 임포트
from backend.models import (
    ClassifyRequest,
    ClassifyResponse,)


# ============================================
# Response Models (conflict_resolver 반환값 기반)
# ============================================



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

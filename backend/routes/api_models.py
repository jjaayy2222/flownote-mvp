# backend/routes/api_models.py

"""
API Models

DEPRECATED: 대부분의 모델이 backend.models로 이동되었습니다.
이 파일은 conflict 전용 모델만 유지합니다.

Conflict 관련 모델:
- ConflictDetectionRequest
- ConflictDetectionResponse
- ConflictResolutionRequest
- ConflictResolutionResponse
"""



from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# 모델 임포트
from backend.models import (
    ErrorResponse,
    SuccessResponse,
    FileMetadata,
    MetadataResponse,
)

# ✅ 공통 모델은 backend.models에서 import
from backend.models import (
    ErrorResponse,
    SuccessResponse,
    FileMetadata,
    MetadataResponse,
)

# ❌ 이 파일에 있던 모델들 삭제:
# class ErrorResponse(BaseModel): ...
# class MetadataResponse(BaseModel): ...
# 등등

# ✅ Conflict 전용 모델만 유지
class ConflictDetectionRequest(BaseModel):
    """충돌 감지 요청"""
    file_id: str = Field(..., description="파일 ID")
    text: str = Field(..., description="분류할 텍스트")
    user_id: Optional[str] = Field(None, description="사용자 ID")


class ConflictDetectionResponse(BaseModel):
    """충돌 감지 응답"""
    conflict_detected: bool = Field(..., description="충돌 감지 여부")
    confidence_gap: Optional[float] = Field(None, description="신뢰도 차이")
    categories: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="후보 카테고리들"
    )


class ConflictResolutionRequest(BaseModel):
    """충돌 해결 요청"""
    file_id: str = Field(..., description="파일 ID")
    selected_category: str = Field(..., description="선택된 카테고리")
    user_id: Optional[str] = Field(None, description="사용자 ID")


class ConflictResolutionResponse(BaseModel):
    """충돌 해결 응답"""
    status: str = Field(default="resolved", description="해결 상태")
    file_id: str = Field(..., description="파일 ID")
    final_category: str = Field(..., description="최종 카테고리")


__all__ = [
    # Re-export from backend.models
    "ErrorResponse",
    "SuccessResponse",
    "FileMetadata",
    "MetadataResponse",
    
    # Conflict-specific models
    "ConflictDetectionRequest",
    "ConflictDetectionResponse",
    "ConflictResolutionRequest",
    "ConflictResolutionResponse",
]

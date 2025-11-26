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


from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime

# ... (imports)


# ✅ Conflict 전용 모델만 유지
class ConflictDetectionRequest(BaseModel):
    """충돌 감지 요청"""

    file_id: str = Field(..., description="파일 ID")
    text: str = Field(..., description="분류할 텍스트")
    user_id: Optional[str] = Field(None, description="사용자 ID")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "file_12345",
                "text": "이 문서는 프로젝트 A의 기획안입니다.",
                "user_id": "user_001",
            }
        }
    )


class ConflictDetectionResponse(BaseModel):
    """충돌 감지 응답"""

    conflict_detected: bool = Field(..., description="충돌 감지 여부")
    confidence_gap: Optional[float] = Field(
        None, description="상위 2개 카테고리의 신뢰도 차이"
    )
    categories: List[Dict[str, Any]] = Field(
        default_factory=list, description="후보 카테고리 목록 (신뢰도 포함)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conflict_detected": True,
                "confidence_gap": 0.05,
                "categories": [
                    {
                        "category": "Projects",
                        "confidence": 0.45,
                        "reason": "프로젝트 관련 키워드 감지",
                    },
                    {
                        "category": "Areas",
                        "confidence": 0.40,
                        "reason": "업무 영역과 유사",
                    },
                ],
            }
        }
    )


class ConflictResolutionRequest(BaseModel):
    """충돌 해결 요청"""

    file_id: str = Field(..., description="파일 ID")
    selected_category: str = Field(..., description="사용자가 선택한 최종 카테고리")
    user_id: Optional[str] = Field(None, description="사용자 ID")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "file_12345",
                "selected_category": "Projects",
                "user_id": "user_001",
            }
        }
    )


class ConflictResolutionResponse(BaseModel):
    """충돌 해결 응답"""

    status: str = Field(default="resolved", description="해결 상태")
    file_id: str = Field(..., description="파일 ID")
    final_category: str = Field(..., description="최종 확정된 카테고리")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "resolved",
                "file_id": "file_12345",
                "final_category": "Projects",
            }
        }
    )


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

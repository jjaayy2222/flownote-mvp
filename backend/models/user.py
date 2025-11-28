# backend/models/user.py

"""
사용자 관련 Pydantic 모델

이 파일은 모든 사용자 관련 모델을 통합합니다:
- Onboarding 관련 (Step1Input, Step2Input, OnboardingStatus)
- Profile 관련 (UserProfile)
- Context 관련 (UserContext)
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime


class Step1Input(BaseModel):
    """
    온보딩 Step 1: 사용자 직업 입력
    
    사용자가 자신의 직업을 입력하는 첫 번째 단계
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "occupation": "개발자",
                "name": "김철수"
            }
        }
    )
    
    occupation: str = Field(..., description="사용자 직업")
    name: str = Field(default="Anonymous", description="사용자 이름")


class Step2Input(BaseModel):
    """
    온보딩 Step 2: 관심 영역 선택
    
    사용자가 관심 있는 영역을 선택하는 두 번째 단계
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "user_123",
                "selected_areas": ["백엔드", "AI", "데이터분석"]
            }
        }
    )
    
    user_id: str = Field(..., description="사용자 ID")
    selected_areas: List[str] = Field(..., description="선택한 관심 영역")


class OnboardingStatus(BaseModel):
    """
    온보딩 상태 조회
    
    사용자의 온보딩 진행 상태를 나타냅니다
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "user_123",
                "occupation": "개발자",
                "areas": ["백엔드", "AI"],
                "is_completed": True
            }
        }
    )

    user_id: str = Field(..., description="사용자 ID")
    occupation: str = Field(..., description="직업")
    areas: List[str] = Field(default_factory=list, description="관심 영역")
    is_completed: bool = Field(default=False, description="온보딩 완료 여부")

class UserProfile(BaseModel):
    """
    사용자 프로필 (CSV 저장용)
    
    사용자의 기본 정보와 관심사를 저장합니다
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "user_123",
                "occupation": "개발자",
                "areas": ["백엔드", "AI"],
                "interests": ["Python", "FastAPI", "ML"],
                "created_at": "2025-11-16T10:00:00",
                "updated_at": "2025-11-16T10:00:00"
            }
        }
    )
    
    user_id: str = Field(..., description="사용자 ID")
    occupation: str = Field(..., description="직업")
    areas: List[str] = Field(default_factory=list, description="관심 영역")
    interests: List[str] = Field(default_factory=list, description="관심사")
    created_at: str = Field(..., description="생성 시각")
    updated_at: str = Field(..., description="수정 시각")


class UserContext(BaseModel):
    """
    사용자 컨텍스트 (JSON 저장용)
    
    분류 시 사용되는 사용자의 컨텍스트 정보
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "user_123",
                "occupation": "개발자",
                "areas": ["백엔드", "AI"],
                "interests": ["Python", "FastAPI"],
                "context_keywords": {
                    "Projects": ["프로젝트", "MVP", "개발"],
                    "Areas": ["백엔드", "API", "데이터베이스"]
                }
            }
        }
    )
    
    user_id: str = Field(..., description="사용자 ID")
    occupation: str = Field(..., description="직업")
    areas: List[str] = Field(default_factory=list, description="관심 영역")
    interests: List[str] = Field(default_factory=list, description="관심사")
    context_keywords: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="PARA 카테고리별 키워드"
    )







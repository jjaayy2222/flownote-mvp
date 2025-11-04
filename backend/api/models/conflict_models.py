# backend/api/models/conflict_models.py

"""
Conflict Detection & Resolution Models

메타데이터 충돌 감지 및 해결을 위한 Pydantic 모델 정의
- ConflictType: 충돌 유형 (category, keyword, timestamp)
- ConflictRecord: 개별 충돌 기록
- ResolutionStrategy: 해결 전략
- ConflictReport: 최종 충돌 보고서
"""

from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4


# ============================================
# Enums
# ============================================

class ConflictType(str, Enum):
    """충돌 유형"""
    CATEGORY_CONFLICT = "category"          # Archives vs Projects vs Areas
    KEYWORD_CONFLICT = "keyword"            # 중복/유사 키워드
    TIMESTAMP_CONFLICT = "timestamp"        # 시간 충돌


class ResolutionMethod(str, Enum):
    """해결 방법"""
    AUTO_BY_CONFIDENCE = "auto_by_confidence"       # 신뢰도 기반 자동 선택
    AUTO_BY_FREQUENCY = "auto_by_frequency"         # 빈도 기반 자동 선택
    AUTO_BY_SIMILARITY = "auto_by_similarity"       # 유사도 기반 통합
    MANUAL_OVERRIDE = "manual_override"             # 사용자 수동 선택
    AUTO_BY_LATEST = "auto_by_latest"               # 최신 타임스탬프
    MANUAL_REVIEW = "manual_review"
    PREFER_LATEST_TIMESTAMP = "prefer_latest_timestamp"
    HYBRID_FUSION = "hybrid_fusion"

class ResolutionStatus(str, Enum):
    """해결 상태"""
    DETECTED = "detected"                   # 감지됨 (미해결)
    RESOLVED = "resolved"                   # 해결됨
    PENDING_REVIEW = "pending_review"       # 검토 대기 중
    REJECTED = "rejected"                   # 거부됨


# ============================================
# Data Models
# ============================================

class ConflictDetail(BaseModel):
    """개별 충돌 상세 정보"""
    
    file_id: str = Field(..., description="파일 ID")
    current_value: Any = Field(..., description="현재 값")
    conflicting_value: Any = Field(..., description="충돌하는 값")
    confidence_score: Optional[float] = Field(
        default=None, 
        ge=0.0, 
        le=1.0,
        description="신뢰도 점수"
    )
    source: str = Field(default="unknown", description="출처")

    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "file_001",
                "current_value": "Projects",
                "conflicting_value": "Archives",
                "confidence_score": 0.85,
                "source": "auto_classifier"
            }
        }


class ConflictRecord(BaseModel):
    """개별 충돌 기록"""
    
    conflict_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="충돌 ID (UUID)"
    )
    type: ConflictType = Field(..., description="충돌 유형")
    description: str = Field(..., description="충돌 설명")
    details: List[ConflictDetail] = Field(
        default_factory=list,
        description="충돌 상세 정보"
    )
    severity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="심각도 (0.0~1.0)"
    )
    detected_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="감지 시간"
    )
    auto_resolvable: bool = Field(
        default=True,
        description="자동 해결 가능 여부"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "conflict_id": "conflict_001",
                "type": "category",
                "description": "카테고리 충돌: Projects vs Archives",
                "details": [
                    {
                        "file_id": "file_001",
                        "current_value": "Projects",
                        "conflicting_value": "Archives",
                        "confidence_score": 0.85,
                        "source": "auto_classifier"
                    }
                ],
                "severity": 0.7,
                "detected_at": "2025-11-04T20:16:00",
                "auto_resolvable": True
            }
        }


class ResolutionStrategy(BaseModel):
    """충돌 해결 전략"""
    
    conflict_id: str = Field(..., description="충돌 ID")
    method: ResolutionMethod = Field(..., description="해결 방법")
    recommended_value: Any = Field(..., description="추천 값")
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="해결 신뢰도"
    )
    reasoning: str = Field(..., description="해결 이유")
    affected_files: List[str] = Field(
        default_factory=list,
        description="영향받는 파일 목록"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "conflict_id": "conflict_001",
                "method": "auto_by_confidence",
                "recommended_value": "Projects",
                "confidence": 0.92,
                "reasoning": "confidence_score가 더 높은 Projects로 통합",
                "affected_files": ["file_001", "file_002"]
            }
        }


class ConflictResolution(BaseModel):
    """충돌 해결 결과"""
    
    conflict_id: str = Field(..., description="충돌 ID")
    status: ResolutionStatus = Field(..., description="해결 상태")
    strategy: ResolutionStrategy = Field(..., description="적용된 전략")
    resolved_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="해결 시간"
    )
    resolved_by: str = Field(
        default="system",
        description="해결 수행자 (system/user)"
    )
    notes: Optional[str] = Field(
        default=None,
        description="추가 노트"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "conflict_id": "conflict_001",
                "status": "resolved",
                "strategy": {
                    "conflict_id": "conflict_001",
                    "method": "auto_by_confidence",
                    "recommended_value": "Projects",
                    "confidence": 0.92,
                    "reasoning": "신뢰도 기반 자동 선택",
                    "affected_files": ["file_001"]
                },
                "resolved_at": "2025-11-04T20:16:05",
                "resolved_by": "system",
                "notes": "자동 해결 완료"
            }
        }


class ConflictReport(BaseModel):
    """종합 충돌 보고서"""
    
    report_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="보고서 ID"
    )
    total_conflicts: int = Field(default=0, description="총 충돌 수")
    detected_conflicts: List[ConflictRecord] = Field(
        default_factory=list,
        description="감지된 충돌 목록"
    )
    resolutions: List[ConflictResolution] = Field(
        default_factory=list,
        description="해결된 충돌 목록"
    )
    conflict_breakdown: Dict[str, int] = Field(
        default_factory=dict,
        description="충돌 유형별 분류"
    )
    auto_resolved_count: int = Field(default=0, description="자동 해결된 수")
    manual_review_needed: int = Field(default=0, description="수동 검토 필요 수")
    resolution_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="해결율 (0.0~1.0)"
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="보고서 생성 시간"
    )
    status: str = Field(
        default="completed",
        description="보고서 상태"
    )
    summary: Optional[str] = Field(
        default=None,
        description="요약"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "report_id": "report_001",
                "total_conflicts": 3,
                "detected_conflicts": [],
                "resolutions": [],
                "conflict_breakdown": {
                    "category": 2,
                    "keyword": 1,
                    "timestamp": 0
                },
                "auto_resolved_count": 3,
                "manual_review_needed": 0,
                "resolution_rate": 1.0,
                "generated_at": "2025-11-04T20:16:10",
                "status": "completed",
                "summary": "모든 충돌이 자동으로 해결되었습니다"
            }
        }


# ============================================
# Request/Response Models for API
# ============================================

class DetectConflictRequest(BaseModel):
    """충돌 감지 요청"""
    
    include_timestamp: bool = Field(
        default=False,
        description="타임스탬프 충돌 포함 여부"
    )
    severity_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="심각도 임계값"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "include_timestamp": False,
                "severity_threshold": 0.3
            }
        }


class ResolveConflictRequest(BaseModel):
    """충돌 해결 요청"""
    
    conflict_id: str = Field(..., description="충돌 ID")
    resolution_method: Optional[ResolutionMethod] = Field(
        default=None,
        description="해결 방법 (지정하지 않으면 자동)"
    )
    manual_resolution: Optional[Any] = Field(
        default=None,
        description="수동 해결 값"
    )
    notes: Optional[str] = Field(
        default=None,
        description="추가 노트"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "conflict_id": "conflict_001",
                "resolution_method": "auto_by_confidence",
                "manual_resolution": None,
                "notes": "자동 해결로 진행"
            }
        }


class ConflictDetectResponse(BaseModel):
    """충돌 감지 응답"""
    
    success: bool = Field(..., description="성공 여부")
    report: ConflictReport = Field(..., description="충돌 보고서")
    message: str = Field(..., description="메시지")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "report": {
                    "report_id": "report_001",
                    "total_conflicts": 3,
                    "auto_resolved_count": 3,
                    "resolution_rate": 1.0
                },
                "message": "충돌 감지 완료"
            }
        }


class ConflictResolveResponse(BaseModel):
    """충돌 해결 응답"""
    
    success: bool = Field(..., description="성공 여부")
    resolution: ConflictResolution = Field(..., description="해결 결과")
    message: str = Field(..., description="메시지")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "resolution": {
                    "conflict_id": "conflict_001",
                    "status": "resolved"
                },
                "message": "충돌이 성공적으로 해결되었습니다"
            }
        }




"""test_result

    ```bash
    python -c "from backend.api.models import ConflictType, ConflictRecord; print('✅ Import successful!')"

    ✅ Import successful!
    ```

"""
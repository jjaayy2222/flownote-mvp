# backend/models/common.py


"""
공통 Pydantic 모델

이 파일은 여러 모듈에서 공통으로 사용하는 모델을 통합합니다:
- API 공통 응답 (ErrorResponse, SuccessResponse)
- 메타데이터 관련 (FileMetadata, MetadataResponse)
- API 요청 (SaveClassificationRequest, SearchRequest)
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class ErrorResponse(BaseModel):
    """
    에러 응답
    
    API에서 에러 발생 시 사용하는 표준 응답 형식
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "ValidationError",
                "detail": "Text field is required",
                "timestamp": "2025-11-16T12:00:00"
            }
        }
    )
    
    error: str = Field(..., description="에러 타입")
    detail: Optional[str] = Field(None, description="에러 상세 내용")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="에러 발생 시각"
    )


class SuccessResponse(BaseModel):
    """
    성공 응답
    
    API 요청 성공 시 사용하는 표준 응답 형식
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "message": "Classification saved successfully",
                "data": {"file_id": "file_123"},
                "timestamp": "2025-11-16T12:00:00"
            }
        }
    )
    
    status: str = Field(default="success", description="응답 상태")
    message: str = Field(..., description="응답 메시지")
    data: Optional[Dict[str, Any]] = Field(None, description="응답 데이터")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="응답 시각"
    )

class FileMetadata(BaseModel):
    """
    파일 메타데이터
    
    업로드된 파일의 기본 정보
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "file_123",
                "filename": "document.pdf",
                "category": "Projects",
                "para_class": "P",
                "created_at": "2025-11-16T12:00:00"
            }
        }
    )
    
    file_id: str = Field(..., description="파일 ID")
    filename: str = Field(..., description="파일명")
    category: str = Field(..., description="PARA 카테고리")
    para_class: str = Field(..., description="PARA 클래스 (P/A/R/A)")
    created_at: Optional[str] = Field(None, description="생성 시각")


class MetadataResponse(BaseModel):
    """
    메타데이터 조회 응답
    
    파일의 상세 메타데이터 정보
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "file_123",
                "para_category": "Projects",
                "keyword_tags": ["프로젝트", "기획"],
                "confidence_score": 0.92,
                "conflict_flag": False,
                "created_at": "2025-11-16T12:00:00"
            }
        }
    )
    
    file_id: str = Field(..., description="파일 ID")
    para_category: str = Field(..., description="PARA 카테고리")
    keyword_tags: List[str] = Field(default_factory=list, description="키워드 태그")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="신뢰도")
    conflict_flag: bool = Field(default=False, description="충돌 플래그")
    created_at: Optional[str] = Field(None, description="생성 시각")


class SaveClassificationRequest(BaseModel):
    """
    분류 결과 저장 요청
    
    분류된 결과를 데이터베이스에 저장할 때 사용
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "file_id": "file_123",
                "classification": {
                    "category": "Projects",
                    "confidence": 0.92,
                    "keyword_tags": ["프로젝트", "기획"]
                }
            }
        }
    )
    
    file_id: str = Field(..., description="파일 ID")
    classification: Dict[str, Any] = Field(..., description="분류 결과")


class SearchRequest(BaseModel):
    """
    검색 요청
    
    파일 또는 메타데이터 검색 시 사용
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "프로젝트 기획",
                "filters": {
                    "category": "Projects",
                    "confidence_min": 0.8
                }
            }
        }
    )
    
    query: str = Field(..., description="검색 쿼리")
    filters: Optional[Dict[str, Any]] = Field(None, description="검색 필터")


class ErrorResponse(BaseModel):
    """에러 응답"""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
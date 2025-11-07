# backend/routes/classifier_routes.py

"""분류 라우트"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional, Any
import logging

from backend.classifier.langchain_integration import (
    classify_with_langchain,
    classify_with_metadata,
    hybrid_classify
)
from backend.services.parallel_processor import ParallelClassifier
from backend.classifier.context_injector import get_context_injector

logger = logging.getLogger(__name__)


# ============ Router 초기화 ============
router = APIRouter()                    # API Router 추가


# ============ 싱글톤 인스턴스 ============
injector = get_context_injector()       # context_injector 싱글톤 초기화



# ============ 요청 스키마들 ============

class ClassificationRequest(BaseModel):
    """텍스트 분류 요청"""
    text: str                       # 분류할 텍스트
    filename: str = "unknown"       # 선택사항
    user_id: Optional[str] = None   # 맥락 주입용
    

class ClassificationResponse(BaseModel):
    """분류 응답"""
    category: str
    confidence: float
    # <--- 나머지 필드들

class MetadataClassifyRequest(BaseModel):
    """메타데이터 분류 요청"""
    metadata: Dict
    user_id: Optional[str] = None


class HybridClassifyRequest(BaseModel): 
    """하이브리드 분류 요청"""
    text: str
    metadata: Dict
    user_id: Optional[str] = None


class ParallelClassifyRequest(BaseModel):
    """병렬 분류 요청 (텍스트 + 메타데이터)"""
    text: str
    metadata: Dict
    filename: str = "unknown"
    user_id: Optional[str] = None


# ============ API 엔드포인트 ============

@router.post("/text")
async def classify_text_endpoint(request: ClassificationRequest):
    """
    텍스트 분류 (LangChain 기반)
    - AI 분석 실행
    - user_id 있으면 맥락 주입
    """
    try:
        # Step 1: AI 분석
        result = classify_with_langchain(request.text)
        
        # Step 2: user_id 있으면 맥락 주입
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        else:
            result["context_injected"] = False
        
        return {
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"텍스트 분류 실패: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/metadata")
async def classify_metadata_endpoint(request: MetadataClassifyRequest):
    """메타데이터 분류"""
    try:
        result = classify_with_metadata(request.metadata)
        
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"메타데이터 분류 실패: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/hybrid")
async def hybrid_classify_endpoint(request: HybridClassifyRequest):
    """텍스트 + 메타데이터 하이브리드 분류"""
    try:
        result = hybrid_classify(request.text, request.metadata)
        
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"하이브리드 분류 실패: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/parallel")
async def parallel_classify_endpoint(request: ParallelClassifyRequest):
    """텍스트 + 메타데이터 병렬 분류"""
    try:
        result = ParallelClassifier.classify_parallel(
            request.text,
            request.metadata
        )
        
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"병렬 분류 실패: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/para")
async def classify_para(request: ClassificationRequest):
    """
    PARA 분류 엔드포인트
    /api/classify/para 로 접근 가능
    """
    try:
        result = classify_with_langchain(request.text)
        # <--- 실제 분류 로직
        return {"category": result, "status": "success"}
    except Exception as e:
        logger.error(f"PARA 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keywords")
async def classify_keywords(request: ClassificationRequest):
    """
    키워드 분류 엔드포인트
    접근: POST http://localhost:8000/api/classify/keywords
    """
    try:
        logger.info(f"키워드 분류 요청: {request.text[:50]}")
        
        # <--- /para와 같은 형식으로 응답해야 함!!
        return {
            "status": "success",
            "category": {  # ✅ category 필드 필수!
                "keywords": ["work", "meeting"],
                "confidence": 0.9
            }
        }
    except Exception as e:
        logger.error(f"키워드 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))











"""test_result




"""
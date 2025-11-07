# backend/routes/classifier_routes.py

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Optional, Any
import logging

from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Optional
from backend.classifier.langchain_integration import (
    classify_with_langchain,
    classify_with_metadata,
    hybrid_classify
)
from backend.services.parallel_processor import ParallelClassifier
from backend.classifier.context_injector import get_context_injector
#from backend.routes.classifier_routes import router as classifier_router

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







"""test_result




"""
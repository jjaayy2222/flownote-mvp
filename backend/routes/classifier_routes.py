# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/routes/classifier_routes.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
분류 라우트
- LangChain 기반 분류
- 사용자 컨텍스트 반영
- 병렬 처리 지원
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional, Any

# 함수 임포트
from backend.classifier.langchain_integration import (
    classify_with_langchain,
    classify_with_metadata,
    hybrid_classify
)
from backend.classifier.context_injector import get_context_injector


# 클래스 임포트 
from backend.classifier.langchain_integration import PARAClassificationOutput
from backend.services.parallel_processor import ParallelClassifier
from backend.classifier.keyword_classifier import KeywordClassifier
from backend.classifier.metadata_classifier import MetadataClassifier
from backend.classifier.para_classifier import PARAClassifier
from backend.classifier.context_injector import ContextInjector
from backend.services.conflict_service import ConflictService
from backend.routes.conflict_routes import ClassifyRequest, ClassifyResponse
from backend.metadata import FileMetadata


import logging

logger = logging.getLogger(__name__)


# ============ Router 초기화 ============
router = APIRouter()                    # API Router 추가


# ============ 싱글톤 인스턴스 ============
# 요청마다 재사용하지 않음
injector = get_context_injector()



# ============ 요청 스키마들 ============

class ClassificationRequest(BaseModel):
    """텍스트 분류 요청"""
    text: str                       # 분류할 텍스트
    filename: str = "unknown"       # 선택사항
    user_id: Optional[str] = None   # 맥락 주입용 / 사용자 컨텍스트용
    

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
    - user_id 있으면 컨텍스트 주입
    """
    try:
        # Step 1: 사용자 컨텍스트 가져오기
        user_areas = []
        if request.user_id:
            try:
                user_context = injector.get_user_context(request.user_id)
                user_areas = user_context.get('areas', [])
                
                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                logger.info(f"📄 새 분류 요청")
                logger.info(f"User ID: {request.user_id}")
                logger.info(f"User Areas: {user_areas}")
                logger.info(f"Text Preview: {request.text[:100]}...")
                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            except Exception as e:
                logger.warning(f"⚠️ Context loading failed: {e}")
        
        # Step 2: AI 분석 (LangChain 사용)
        # ⚠️ 주의: classify_with_langchain은 매번 새로운 분석을 수행해야 함!
        result = classify_with_langchain(request.text)
        
        # Step 3: 사용자 컨텍스트 주입
        if request.user_id and user_areas:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
            result["context_injected"] = True
            result["user_areas"] = user_areas
        else:
            result["context_injected"] = False
            result["user_areas"] = []

        # Step 4: 디버깅 로그
        logger.info(f"✅ 분류 완료:")
        logger.info(f"  - Category: {result.get('category', 'N/A')}")
        logger.info(f"  - Tags: {result.get('tags', [])[:5]}")
        logger.info(f"  - Context Injected: {result.get('context_injected', False)}")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        return {
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"❌ 텍스트 분류 실패: {str(e)}", exc_info=True)
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
        logger.error(f"❌ 메타데이터 분류 실패: {str(e)}")
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
        logger.error(f"❌ 하이브리드 분류 실패: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/parallel")
async def parallel_classify_endpoint(request: ParallelClassifyRequest):
    """텍스트 + 메타데이터 병렬 분류"""
    try:
        # ⚠️ 주의: ParallelClassifier.classify_parallel은 정적 메서드!
        # → 매번 새로운 분석을 수행함
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
        logger.error(f"❌ 병렬 분류 실패: {str(e)}")
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
        
        # 사용자 컨텍스트 주입
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "category": result.get("category", "Resources"),
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"❌ PARA 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keywords")
async def classify_keywords(request: ClassificationRequest):
    """
    키워드 분류 엔드포인트
    접근: POST http://localhost:8000/api/classify/keywords
    """
    try:
        logger.info(f"🔍 키워드 분류 요청: {request.text[:50]}...")
        
        # ⚠️ 주의: classify_with_langchain은 매번 새로운 LLM 호출!
        result = classify_with_langchain(request.text)
        
        # 사용자 컨텍스트 주입
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "status": "success",
            "category": {
                "keywords": result.get("tags", []),
                "confidence": result.get("confidence", 0.8)
            },
            "result": result
        }
    
    except Exception as e:
        logger.error(f"❌ 키워드 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))











"""test_result




"""
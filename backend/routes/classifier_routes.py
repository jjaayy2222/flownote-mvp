# backend/routes/classifier_routes.py

from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Optional
from backend.classifier.langchain_integration import (
    classify_with_langchain,
    classify_with_metadata,
    hybrid_classify
)
from backend.services.parallel_processor import ParallelClassifier

app = FastAPI()
router = APIRouter()                # FastAPI Router 추가

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 요청 스키마들 ============

class ClassificationRequest(BaseModel):
    """텍스트 분류 요청"""
    text: str                   # 분류할 텍스트
    filename: str = "unknown"   # 선택사항
    

class MetadataClassifyRequest(BaseModel):
    """메타데이터 분류 요청"""
    metadata: Dict


class HybridClassifyRequest(BaseModel): 
    """하이브리드 분류 요청"""
    text: str
    metadata: Dict


class ParallelClassifyRequest(BaseModel):
    """병렬 분류 요청 (텍스트 + 메타데이터)"""
    text: str
    metadata: Dict
    filename: str = "unknown"


# ============ API 엔드포인트 ============
    
@router.post("/api/classify/text")
async def classify_text_endpoint(request: ClassificationRequest):
    """텍스트 분류 (LangChain)"""
    try:
        result = classify_with_langchain(request.text)
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/api/classify/metadata")
async def classify_metadata_endpoint(request: MetadataClassifyRequest):
    """메타데이터만 분류"""
    try:
        result = classify_with_metadata(request.metadata)
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/api/classify/hybrid")
async def hybrid_classify_endpoint(request: HybridClassifyRequest):
    """텍스트 + 메타 하이브리드 분류"""
    try:
        result = hybrid_classify(request.text, request.metadata)
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# @router 사용
@router.post("/api/classify/parallel")                                   
async def parallel_classify_endpoint(request: ParallelClassifyRequest):
    """텍스트 + 메타 병렬 분류"""
    try:
        result = ParallelClassifier.classify_parallel(
            request.text,
            request.metadata
        )
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# ============ Router 등록 ============
app.include_router(router) 



"""test_result




"""
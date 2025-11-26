# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/routes/classifier_routes.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
통합 분류 라우터 (Phase 4 Refactor)

이 파일은 "Thin Router" 패턴을 따릅니다.
모든 비즈니스 로직은 `ClassificationService`로 이관되었습니다.
"""

import os
import json
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 모델 Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from backend.models import (
    ClassifyRequest,
    ClassifyResponse,
    # ClassificationRequest,  # Unused
    # ClassificationResponse, # Unused
    # ClassifyBatchRequest,   # Unused
    # ClassifyBatchResponse,  # Unused
    # MetadataClassifyRequest, # Unused
    # HybridClassifyRequest,   # Unused
    # ParallelClassifyRequest, # Unused
    # FileMetadata,           # Unused
    # SaveClassificationRequest, # Unused
    # SearchRequest,          # Unused
    # HealthCheckResponse,    # Unused
    # MetadataResponse,       # Unused
    # ErrorResponse,          # Unused
    # SuccessResponse,        # Unused
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 서비스 Import (Refactored)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from backend.services.classification_service import ClassificationService

# ❌ Removed / Moved to Service
# from backend.classifier.langchain_integration import ...
# from backend.classifier.context_injector import get_context_injector
# from backend.classifier.para_agent import run_para_agent
# from backend.data_manager import save_json_log, DataManager
# from backend.services.conflict_service import ConflictService
# from backend.classifier.keyword_classifier import KeywordClassifier
# from backend.services.parallel_processor import ParallelClassifier
# from backend.chunking import TextChunker
# ...

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Router & Service Instance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
router = APIRouter()

# 싱글톤 서비스 인스턴스
classification_service = ClassificationService()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API 엔드포인트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post(
    "/classify",
    response_model=ClassifyResponse,
    tags=["Classification", "Main API", "Text"],
)
async def classify_text(request: ClassifyRequest):
    """
    메인 텍스트 분류 API

    PARA 방법론을 기반으로 입력된 텍스트를 분류합니다.
    사용자의 직업(occupation)과 관심 영역(areas)을 고려하여 개인화된 분류를 수행합니다.

    - **text**: 분류할 텍스트 (필수)
    - **user_id**: 사용자 식별자 (선택)
    - **occupation**: 사용자 직업 (선택, 프롬프트 최적화용)
    - **areas**: 사용자 관심 영역 리스트 (선택, Areas 매칭용)
    - **interests**: 사용자 관심사 리스트 (선택)

    Returns:
        ClassifyResponse: 분류 결과 (카테고리, 신뢰도, 근거, 태그 등)
    """
    try:
        # Refactored: Logic moved to ClassificationService
        return await classification_service.classify(
            text=request.text,
            user_id=request.user_id,
            file_id=request.file_id,
            occupation=request.occupation,
            areas=request.areas,
            interests=request.interests,
        )

    except Exception as e:
        logger.error(f"❌ 분류 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"분류 실패: {str(e)}")


@router.post(
    "/file",
    response_model=ClassifyResponse,
    tags=["Classification", "Main API", "File Upload"],
)
async def classify_file_main(
    request: Request,
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    file_id: Optional[str] = Form(None),
    occupation: Optional[str] = Form(None),
    areas: Optional[str] = Form(None),
    interests: Optional[str] = Form(None),
    selected_category: Optional[str] = Form(None),
):
    """
    메인 파일 분류 API

    업로드된 파일을 텍스트로 변환한 후 PARA 분류를 수행합니다.
    현재 지원 형식: .txt, .md, .pdf (텍스트 추출 가능 시)

    - **file**: 업로드할 파일 (Multipart Form)
    - **user_id**: 사용자 식별자 (Form)
    - **occupation**: 사용자 직업 (Form)
    - **areas**: JSON 문자열로 된 관심 영역 리스트 (Form)

    Returns:
        ClassifyResponse: 분류 결과
    """
    try:
        # Step 1: 파일 읽기
        content = await file.read()
        text = (
            content.decode("utf-8", errors="ignore")
            if isinstance(content, (bytes, bytearray))
            else str(content)
        )

        # Step 2: Form 데이터 파싱
        areas_list = []
        if areas:
            try:
                areas_list = json.loads(areas)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON format for areas: {areas}")
                areas_list = []

        interests_list = []
        if interests:
            try:
                interests_list = json.loads(interests)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON format for interests: {interests}")
                interests_list = []

        # 사용자 ID 결정 (Form > Request State > Anonymous)
        effective_user_id = (
            user_id or getattr(request.state, "user_id", None) or "anonymous"
        )

        # Refactored: Logic moved to ClassificationService
        return await classification_service.classify(
            text=text,
            user_id=effective_user_id,
            file_id=file_id or file.filename,
            occupation=occupation,
            areas=areas_list,
            interests=interests_list,
        )

    except Exception as e:
        logger.error(f"❌ 파일 분류 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

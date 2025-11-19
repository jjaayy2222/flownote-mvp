# backend/routes/conflict_routes.py

"""
분류 API 라우트
"""

import asyncio
import logging
import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List


from backend.classifier.para_agent import run_para_agent_sync
from backend.api.endpoints.conflict_resolver_agent import resolve_conflicts_sync
from backend.services.conflict_service import ConflictService, KeywordClassifier

# 통합 모델 마이그레이션 임포트 
from backend.models.classification import (
    ClassifyResponse,
    ClassifyRequest,
    SaveClassificationRequest,)
from backend.models.common import(
    SearchRequest,
    SuccessResponse,
    ErrorResponse,
    MetadataResponse,
)
from backend.models.conflict import (
    ConflictRecord,
    ConflictReport
)

logger = logging.getLogger(__name__)

#router = APIRouter(prefix="/api/classify", tags=["classification"])
router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
async def classify_text(request: ClassifyRequest):
    """
    텍스트 분류 API
    
    - 매번 새로운 KeywordClassifier 인스턴스 생성
    - 매번 새로운 keyword_tags 생성
    - DB 및 로그에 저장
    """
    try:
        logger.info(f"🔍 분류 요청: text={request.text[:50]}...")
        logger.info(f"  - user_id: {request.user_id}")
        logger.info(f"  - file_id: {request.file_id}")
        
        # ============================================================
        # Step 1: PARA 분류
        # ============================================================
        para_result = run_para_agent_sync(
            text=request.text,
            metadata={
                "user_id": request.user_id,
                "file_id": request.file_id
            }
        )
        
        logger.info(f"✅ PARA 분류 결과: {para_result.get('category')}")
        
        # ============================================================
        # Step 2: 키워드 추출 (매번 새 인스턴스!)
        # ============================================================
        keyword_classifier = KeywordClassifier()  # ✅ 새 인스턴스!
        
        keyword_result = keyword_classifier.classify(
            text=request.text,
            user_context={
                "user_id": request.user_id,
                "file_id": request.file_id
            }
        )
        
        # ✅ keyword_tags 추출 (기본값 보장)
        new_keyword_tags = keyword_result.get('tags', ['기타'])
        logger.info(f"✅ 새 키워드 생성: {new_keyword_tags}")
        
        # ============================================================
        # Step 3: 충돌 해결
        # ============================================================
        conflict_service = ConflictService()
        conflict_result = conflict_service.resolve_conflict(
            para_result=para_result,
            keyword_result=keyword_result,
            text=request.text
        )
        
        logger.info(f"✅ 충돌 해결 완료!")
        logger.info(f"  - final_category: {conflict_result.get('final_category')}")
        logger.info(f"  - keyword_tags: {conflict_result.get('keyword_tags')}")
        
        # ============================================================
        # Step 4: DB 저장 (✅ 추가!)
        # ============================================================
        try:
            from backend.database.metadata_schema import ClassificationMetadataExtender
            from backend.data_manager import DataManager
            
            # DB에 분류 결과 저장
            db_extender = ClassificationMetadataExtender()
            file_id = db_extender.save_classification_result(
                result={
                    "category": conflict_result.get('final_category'),
                    "keyword_tags": new_keyword_tags,
                    "confidence": conflict_result.get('confidence', 0.0),
                    "conflict_detected": conflict_result.get('conflict_detected', False),
                    "snapshot_id": para_result.get('snapshot_id', ''),
                    "reasoning": conflict_result.get('reason', '')
                },
                filename=request.file_id or f"text_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            
            logger.info(f"✅ DB 저장 완료: file_id={file_id}")
            
            # 로그 파일에 기록 (✅ 추가!)
            data_manager = DataManager()
            data_manager.log_classification(
                user_id=request.user_id or "anonymous",
                file_name=request.file_id or "unknown",
                ai_prediction=conflict_result.get('final_category'),
                user_selected=None,  # 사용자가 선택하기 전
                confidence=conflict_result.get('confidence', 0.0)
            )
            
            logger.info(f"✅ 로그 기록 완료")
            
        except Exception as db_error:
            logger.error(f"⚠️ DB 저장 실패 (무시): {db_error}")
        
        # ============================================================
        # Step 5: 응답 반환
        # ============================================================
        response = ClassifyResponse(
            category=conflict_result.get('final_category', para_result.get('category', '기타')),
            confidence=conflict_result.get('confidence', para_result.get('confidence', 0.0)),
            snapshot_id=str(para_result.get('snapshot_id', '')),
            conflict_detected=conflict_result.get('conflict_detected', False),
            requires_review=conflict_result.get('requires_review', False),
            keyword_tags=new_keyword_tags,  # ✅ 새 키워드
            reasoning=conflict_result.get('reason', ''),
            user_context="",
            user_profile={},
            context_injected=False
        )
        
        logger.info(f"✅ 분류 완료!")
        logger.info(f"  - category: {response.category}")
        logger.info(f"  - keyword_tags: {response.keyword_tags}")
        logger.info(f"  - confidence: {response.confidence}")
        
        return response
    
    except Exception as e:
        logger.error(f"❌ 분류 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"분류 실패: {str(e)}")

@router.post("/resolve")
async def resolve_conflicts(conflicts: List[ConflictRecord]) -> ConflictReport:
    """
    충돌 해결 엔드포인트 (비동기 wrapper)
    """
    from backend.api.endpoints.conflict_resolver_agent import resolve_conflicts_sync
    result = await asyncio.to_thread(resolve_conflicts_sync, conflicts)
    return result

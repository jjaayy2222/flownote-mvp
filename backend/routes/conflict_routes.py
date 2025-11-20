# backend/routes/conflict_routes.py

"""
충돌 해결 라우터 (Phase 3.2)

이 파일은 충돌 감지 및 해결 관련 엔드포인트를 제공합니다:
- 충돌 감지 및 자동 분류 (classify)
- 충돌 해결 (resolve)
"""

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 모델 Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from backend.models import (
    ClassifyRequest,
    ClassifyResponse,
    ConflictRecord,
    ConflictReport,
    ConflictDetectResponse,
    ConflictResolveResponse,
    ResolveConflictRequest,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 서비스 및 유틸리티 Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from backend.classifier.para_agent import run_para_agent
from backend.services.conflict_service import ConflictService, KeywordClassifier
from backend.database.metadata_schema import ClassificationMetadataExtender
from backend.data_manager import DataManager
from backend.api.endpoints.conflict_resolver_agent import resolve_conflicts_sync
import asyncio

logger = logging.getLogger(__name__)

# Prefix 제거 (main.py에서만 설정)
router = APIRouter()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 1: 충돌 감지 & 분류
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post(
    "/classify",
    response_model=ClassifyResponse,
    tags=["Conflict", "Detection", "Classify"],
)
async def classify_text(request: ClassifyRequest):
    """
    충돌 감지 텍스트 분류 API

    Tags:
    - Conflict (대분류): 충돌 해결 기능
    - Detection (중분류): 충돌 감지
    - Classify (소분류): 텍스트 분류

    Features:
    - PARA Agent와 Keyword Classifier를 동시에 실행하여 충돌 감지
    - ConflictService를 통해 충돌 자동 해결 시도
    - 결과 DB 및 로그 저장

    Example:
        POST /conflict/classify
        {
            "text": "프로젝트 완성하기",
            "user_id": "user_123",
            "occupation": "개발자",
            "areas": ["백엔드", "AI"]
        }
    """
    try:
        logger.info(f"📝 충돌 감지 분류 요청: text={request.text[:50]}...")
        logger.info(f"  - user_id: {request.user_id}")
        logger.info(f"  - file_id: {request.file_id}")

        # ============================================================
        # Step 1: 사용자 컨텍스트 생성
        # ============================================================
        user_context = {
            "user_id": request.user_id,
            "file_id": request.file_id,
            "occupation": request.occupation or "일반 사용자",
            "areas": request.areas or [],
            "interests": request.interests or [],
            "context_keywords": {
                area: [area, f"{area} 관련", f"{area} 업무"]
                for area in (request.areas or [])
            },
        }

        # ============================================================
        # Step 2: PARA 분류 (Async)
        # ============================================================
        try:
            para_result = await run_para_agent(text=request.text, metadata=user_context)
            logger.info(f"✅ PARA 분류 완료: {para_result.get('category')}")
        except Exception as para_error:
            logger.error(f"❌ PARA 분류 실패: {para_error}", exc_info=True)
            para_result = {
                "category": "Resources",
                "confidence": 0.0,
                "snapshot_id": f"snap_failed_{int(datetime.now().timestamp())}",
            }

        # ============================================================
        # Step 3: 키워드 추출 (매번 새 인스턴스!)
        # ============================================================
        keyword_classifier = KeywordClassifier()

        # aclassify 사용 (classifier_routes.py와 동일하게)
        keyword_result = await keyword_classifier.aclassify(
            text=request.text, user_context=user_context
        )

        # 키워드 태그 안전 추출
        new_keyword_tags = keyword_result.get("tags", ["기타"])
        if not isinstance(new_keyword_tags, list):
            new_keyword_tags = [str(new_keyword_tags)] if new_keyword_tags else ["기타"]

        logger.info(f"✅ 키워드 분류 완료: {new_keyword_tags[:3]}...")

        # ============================================================
        # Step 4: 충돌 해결
        # ============================================================
        conflict_service = ConflictService()

        # classify_text 메서드 사용 (통합 로직)
        conflict_result = await conflict_service.classify_text(
            para_result=para_result,
            keyword_result=keyword_result,
            text=request.text,
            user_context=user_context,
        )

        logger.info(f"✅ 충돌 해결 완료: {conflict_result.get('final_category')}")

        # ============================================================
        # Step 5: DB 및 로그 저장
        # ============================================================
        final_category = (
            conflict_result.get("final_category")
            or para_result.get("category")
            or "Resources"
        )

        try:
            # 1. DB 저장
            db_extender = ClassificationMetadataExtender()
            file_id = db_extender.save_classification_result(
                result={
                    "category": final_category,
                    "keyword_tags": new_keyword_tags,
                    "confidence": conflict_result.get("confidence", 0.0),
                    "conflict_detected": conflict_result.get(
                        "conflict_detected", False
                    ),
                    "snapshot_id": para_result.get("snapshot_id", ""),
                    "reasoning": conflict_result.get("reason", ""),
                },
                filename=request.file_id
                or f"text_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            )
            logger.info(f"✅ DB 저장 완료: file_id={file_id}")

            # 2. 로그 파일 기록
            data_manager = DataManager()
            data_manager.log_classification(
                user_id=request.user_id or "anonymous",
                file_name=request.file_id or "unknown",
                ai_prediction=final_category,
                user_selected=None,
                confidence=conflict_result.get("confidence", 0.0),
            )
            logger.info(f"✅ 로그 기록 완료")

        except Exception as db_error:
            logger.warning(f"⚠️ DB/로그 저장 실패 (무시): {db_error}")

        # ============================================================
        # Step 6: 응답 반환
        # ============================================================
        response = ClassifyResponse(
            category=final_category,
            confidence=conflict_result.get(
                "confidence", para_result.get("confidence", 0.0)
            ),
            snapshot_id=str(para_result.get("snapshot_id", "")),
            conflict_detected=conflict_result.get("conflict_detected", False),
            requires_review=conflict_result.get("requires_review", False),
            keyword_tags=new_keyword_tags,
            reasoning=conflict_result.get("reason", ""),
            user_context_matched=keyword_result.get("user_context_matched", False),
            user_areas=request.areas or [],
            user_context=user_context,
            context_injected=bool(request.areas),
        )

        return response

    except Exception as e:
        logger.error(f"❌ 분류 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"분류 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 2: 충돌 해결
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/resolve", tags=["Conflict", "Resolution", "Auto"])
async def resolve_conflicts(conflicts: List[ConflictRecord]) -> ConflictReport:
    """
    충돌 해결 엔드포인트 (비동기 wrapper)

    Tags:
    - Conflict (대분류): 충돌 해결 기능
    - Resolution (중분류): 충돌 해결
    - Auto (소분류): 자동 해결

    Features:
    - 여러 충돌 레코드를 한번에 처리
    - 자동 해결 알고리즘 적용
    - 해결 리포트 반환

    Example:
        POST /conflict/resolve
        [
            {
                "id": "conflict_1",
                "para_category": "Projects",
                "keyword_category": "Areas",
                "confidence_gap": 0.15
            }
        ]
    """
    result = await asyncio.to_thread(resolve_conflicts_sync, conflicts)
    return result

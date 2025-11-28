# backend/routes/conflict_routes.py

"""
충돌 해결 전용 라우터
- 디버깅 및 분석 목적
- 수동 충돌 해결 인터페이스
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException
from backend.models import ConflictRecord, ConflictReport
from backend.services.conflict_service import ConflictService

logger = logging.getLogger(__name__)
router = APIRouter()

conflict_service = ConflictService()


@router.post("/resolve", response_model=ConflictReport, tags=["Conflict", "Resolution"])
async def resolve_conflicts(conflicts: List[ConflictRecord]):
    """충돌 레코드 일괄 해결

    Args:
        conflicts: 충돌 레코드 리스트

    Returns:
        ConflictReport: 해결 결과 리포트

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
    try:
        # ConflictService의 기존 로직 사용
        result = await conflict_service.resolve_batch(conflicts)
        logger.info(f"✅ 충돌 {len(conflicts)}개 해결 완료")
        return result
    except Exception as e:
        logger.error(f"❌ 충돌 해결 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshots", tags=["Conflict", "History"])
async def get_snapshots():
    """저장된 스냅샷 조회 (디버깅용)"""
    return {"snapshots": conflict_service.get_snapshots()}

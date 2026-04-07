# backend/api/endpoints/admin.py

"""Admin Endpoints"""

import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.config import AdminConfig
from backend.services.eval_service import generate_eval_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/eval-report", summary="AI 실패 분석 보고서 생성 (키워드 클러스터링)")
async def get_eval_report_endpoint(
    x_admin_key: Optional[str] = Header(None, description="어드민 인증 키")
):
    """
    [Step 2-3] 관리자 대시보드용 AI 실패 응답 분석 보고서를 반환합니다.
    - 실패 응답들의 질문(Q)에서 핵심 키워드 추출 및 클러스터링 (TF 기반)
    - 가장 자주 실패하는 주제 Top 5 리스트 반환
    """
    admin_key = AdminConfig.get_admin_key()
    
    if not admin_key:
        logger.error("[OBS] ADMIN_API_KEY is not configured in environment.")
        raise HTTPException(status_code=500, detail="Server Configuration Error")
        
    provided = str(x_admin_key or "")
    expected = str(admin_key or "")
    
    if not hmac.compare_digest(provided, expected):
        logger.warning("[OBS] Unauthorized attempt to access admin eval report.")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Admin Key")
        
    try:
        report = await generate_eval_report()
        return report
    except Exception:
        logger.exception("[OBS] Error generating eval report")
        raise HTTPException(status_code=500, detail="Internal Server Error")

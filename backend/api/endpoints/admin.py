# backend/api/endpoints/admin.py

"""Admin Endpoints"""

import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from pydantic import BaseModel, Field

from backend.config import AdminConfig
from backend.services.eval_service import generate_eval_report
from backend.services.finetune_service import set_active_finetune_model

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

class ActiveModelRequest(BaseModel):
    model_id: str = Field(
        ...,
        min_length=3,
        max_length=128,
        pattern=r"^[a-zA-Z0-9\-\.:]+$",
        description="The ID of the model to activate (e.g., ft:gpt-4o:my-org::123 or gpt-4o)"
    )

@router.post("/models/active", summary="활성 파인튜닝 모델 수동 변경 (Hot-swap)")
async def set_active_model_endpoint(
    request: ActiveModelRequest,
    x_admin_key: Optional[str] = Header(None, description="어드민 인증 키")
):
    """
    [Hot-swap] 시스템 전역에서 사용할 파인튜닝 모델 ID를 수동으로 지정합니다.
    - 입력받은 ft-model-id를 Redis 설정(v9:finetune:current_model_id)에 갱신
    """
    admin_key = AdminConfig.get_admin_key()
    
    if not admin_key:
        logger.error("[OBS] ADMIN_API_KEY is not configured in environment.")
        raise HTTPException(status_code=500, detail="Server Configuration Error")
        
    provided = str(x_admin_key or "")
    expected = str(admin_key or "")
    
    if not hmac.compare_digest(provided, expected):
        logger.warning(
            "[OBS] Unauthorized attempt to update active model.",
            extra={"model_id": request.model_id}
        )
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Admin Key")
        
    try:
        await set_active_finetune_model(request.model_id)
        return {"status": "success", "active_model_id": request.model_id}
    except Exception:
        logger.exception(
            "[OBS] Error setting active model",
            extra={"model_id": request.model_id}
        )
        raise HTTPException(status_code=500, detail="Internal Server Error")

from backend.api.models import ModelPerformanceComparison

@router.get("/models/performance", response_model=ModelPerformanceComparison, summary="이전 모델과 현행 파인튜닝 모델 간의 성능 비교 분석 자동화 (User Rating 기반)")
async def get_model_performance_endpoint(
    x_admin_key: Optional[str] = Header(None, description="어드민 인증 키")
):
    """
    [v9.0 Phase 1] 이전 파인튜닝 모델과 최신 파인튜닝 모델의 성능을 비교 분석합니다.
    - User Rating(Thumbs Up/Down) 기준
    - 시간 기반(모델 배포 시간 전/후) 스코어 산출
    """
    admin_key = AdminConfig.get_admin_key()
    
    if not admin_key:
        logger.error("[OBS] ADMIN_API_KEY is not configured in environment.")
        raise HTTPException(status_code=500, detail="Server Configuration Error")
        
    provided = str(x_admin_key or "")
    expected = str(admin_key or "")
    
    if not hmac.compare_digest(provided, expected):
        logger.warning("[OBS] Unauthorized attempt to check model performance.")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Admin Key")
        
    try:
        from backend.services.finetune_service import get_model_performance_comparison
        data = await get_model_performance_comparison()
        
        return ModelPerformanceComparison(
            status="success",
            previous_model_id=data["previous_model_id"],
            current_model_id=data["current_model_id"],
            deployed_at=data["deployed_at"],
            previous_up=data["previous_up"],
            previous_down=data["previous_down"],
            previous_score=data["previous_score"],
            current_up=data["current_up"],
            current_down=data["current_down"],
            current_score=data["current_score"],
            score_improvement=data["score_improvement"]
        )
    except Exception:
        logger.exception("[OBS] Error calculating model performance comparison")
        raise HTTPException(status_code=500, detail="Internal Server Error")

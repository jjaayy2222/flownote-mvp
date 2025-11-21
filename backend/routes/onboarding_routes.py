# backend/routes/onboarding_routes.py

"""
Onboarding Routes (Phase 4.1)

사용자 온보딩 플로우 관련 API 엔드포인트:
- Step 1: 사용자 직업 입력 (step1)
- Step 2: GPT-4o 영역 추천 (suggest-areas)
- Step 3: 영역 선택 저장 (save-context)
- Step 4: 온보딩 상태 확인 (status)

Refactored:
- 비즈니스 로직을 OnboardingService로 이관
- 라우터는 요청/응답 처리만 담당 (Thin Router)
"""

import logging
from fastapi import APIRouter, HTTPException, Query

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 모델 Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from backend.models import Step1Input, Step2Input

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 서비스 Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from backend.services.onboarding_service import OnboardingService

logger = logging.getLogger(__name__)

# Prefix 제거 (main.py에서만 설정)
router = APIRouter()

# 싱글톤 인스턴스
onboarding_service = OnboardingService()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 1: 사용자 프로필 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/step1", response_model=dict, tags=["Onboarding", "User Setup", "Step 1"])
async def onboarding_step1(input_data: Step1Input):
    """
    Step 1: 사용자 직업 입력

    Features:
    - OnboardingService를 통해 사용자 생성
    """
    result = onboarding_service.create_user(
        occupation=input_data.occupation, name=input_data.name
    )

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    # 다음 단계 안내 추가 (기존 응답 호환성 유지)
    result["next_step"] = (
        f"/onboarding/suggest-areas?user_id={result['user_id']}&occupation={result['occupation']}"
    )

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 2: 영역 추천 (GPT-4o)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/suggest-areas", tags=["Onboarding", "AI Suggestion", "Step 2"])
async def suggest_areas(user_id: str = Query(...), occupation: str = Query(...)):
    """
    Step 2: 직업 기반 영역 추천
    """
    result = onboarding_service.suggest_areas(user_id, occupation)

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 3: 컨텍스트 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/save-context", tags=["Onboarding", "Context", "Step 3"])
async def save_context(input_data: Step2Input):
    """
    Step 3: 사용자가 선택한 영역 저장
    """
    result = onboarding_service.save_user_context(
        user_id=input_data.user_id, selected_areas=input_data.selected_areas
    )

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 4: 상태 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/status/{user_id}", tags=["Onboarding", "Status"])
async def get_status(user_id: str):
    """
    온보딩 완료 여부 확인
    """
    result = onboarding_service.get_user_status(user_id)

    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])

    return result

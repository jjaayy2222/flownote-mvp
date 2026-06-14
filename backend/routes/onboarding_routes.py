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
from typing import Any, TypedDict

from fastapi import APIRouter, HTTPException, Query

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 타입 정의
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ServiceResponse(TypedDict, total=False):
    """서비스 결과 응답 구조 정의"""

    status: str
    message: str


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


# 헬퍼 함수: 서비스 에러 처리 헬퍼
def handle_service_error(result: ServiceResponse) -> None:
    """
    서비스 결과에서 에러를 확인하고 HTTPException을 발생시킵니다.

    Args:
        result: 서비스 메서드의 반환 dict (status, message 필드 포함)

    Raises:
        HTTPException: result["status"]가 "error"인 경우 400 에러 발생
    """
    if result.get("status") == "error":
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "요청 처리 중 오류가 발생했습니다."),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 1: 사용자 프로필 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/step1", response_model=dict, tags=["Onboarding", "User Setup", "Step 1"])
async def onboarding_step1(input_data: Step1Input):
    """
    Step 1: 사용자 직업 입력 및 프로필 생성

    사용자의 이름과 직업을 입력받아 초기 프로필을 생성합니다.
    생성된 user_id는 이후 단계에서 계속 사용됩니다.

    - **occupation**: 사용자 직업 (예: 개발자, 디자이너)
    - **name**: 사용자 이름 (선택)

    Returns:
        dict: 생성된 사용자 정보 (user_id, occupation 등)
    """
    result = onboarding_service.create_user(
        occupation=input_data.occupation, name=input_data.name
    )

    handle_service_error(result)

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
    Step 2: 직업 기반 관심 영역 추천 (AI)

    GPT-4o를 사용하여 입력된 직업에 적합한 PARA Areas(책임 영역)를 추천합니다.
    사용자는 이 중에서 자신의 관심사를 선택하게 됩니다.

    - **user_id**: 사용자 ID
    - **occupation**: 직업

    Returns:
        dict: 추천된 영역 리스트 (suggested_areas)
    """
    result = onboarding_service.suggest_areas(user_id, occupation)

    handle_service_error(result)

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 3: 컨텍스트 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/save-context", tags=["Onboarding", "Context", "Step 3"])
async def save_context(input_data: Step2Input):
    """
    Step 3: 사용자 컨텍스트 저장 및 온보딩 완료

    사용자가 선택한 관심 영역을 저장하고, 이를 바탕으로 분류 컨텍스트를 생성합니다.
    이 단계가 완료되면 온보딩이 종료됩니다.

    - **user_id**: 사용자 ID
    - **selected_areas**: 사용자가 선택한 영역 리스트

    Returns:
        dict: 저장 결과 및 생성된 컨텍스트 키워드
    """
    result = onboarding_service.save_user_context(
        user_id=input_data.user_id, selected_areas=input_data.selected_areas
    )

    handle_service_error(result)

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 4: 상태 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/status/{user_id}", tags=["Onboarding", "Status"])
async def get_status(user_id: str):
    """
    온보딩 상태 확인

    특정 사용자의 온보딩 완료 여부와 현재 저장된 정보를 조회합니다.

    - **user_id**: 사용자 ID

    Returns:
        dict: 온보딩 상태 (is_completed, occupation, areas 등)
    """
    result = onboarding_service.get_user_status(user_id)

    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])

    return result

# backend/routes/onboarding_routes.py

"""
Onboarding Routes (Phase 3.3)

사용자 온보딩 플로우 관련 API 엔드포인트:
- Step 1: 사용자 직업 입력 (step1)
- Step 2: GPT-4o 영역 추천 (suggest-areas)
- Step 3: 영역 선택 저장 (save-context)
- Step 4: 온보딩 상태 확인 (status)
"""

import logging
import uuid
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 모델 Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from backend.models import Step1Input, Step2Input, UserProfile, UserContext

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 서비스 및 유틸리티 Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from backend.data_manager import DataManager
from backend.services.gpt_helper import get_gpt_helper

logger = logging.getLogger(__name__)

# Prefix 제거 (main.py에서만 설정)
router = APIRouter()

# 인스턴스 생성
data_manager = DataManager()
gpt_helper = get_gpt_helper()  # 싱글톤


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 1: 사용자 프로필 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/step1", response_model=dict, tags=["Onboarding", "User Setup", "Step 1"])
async def onboarding_step1(input_data: Step1Input):
    """
    Step 1: 사용자 직업 입력

    Tags:
    - Onboarding (대분류): 온보딩 기능
    - User Setup (중분류): 사용자 설정
    - Step 1 (소분류): 1단계

    Features:
    - user_id 자동 생성
    - users_profiles.csv에 저장
    - areas는 아직 빈 상태

    Example:
        POST /onboarding/step1
        {
            "occupation": "교사",
            "name": "Jay"
        }

    Returns:
        {
            "status": "success",
            "user_id": "user_...",
            "message": "Step 1 완료!"
        }
    """
    try:
        # 1. user_id 자동 생성
        user_id = f"user_{str(uuid.uuid4())[:8]}"
        logger.info(
            f"[Step1] Generated user_id: {user_id}, occupation: {input_data.occupation}"
        )

        # 2.users_profiles.csv에 저장 (areas는 아직 빈 상태)
        data_manager.save_user_profile(
            user_id=user_id,
            occupation=input_data.occupation,
            areas="",  # 아직 선택 안 함
            interests="",
        )

        return {
            "status": "success",
            "user_id": user_id,
            "occupation": input_data.occupation,
            "message": "Step 1 완료! 이제 영역을 추천받으세요",
            "next_step": f"/onboarding/suggest-areas?user_id={user_id}&occupation={input_data.occupation}",
        }

    except Exception as e:
        logger.error(f"[Step1] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Step 1 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 2: GPT-4o 영역 추천
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/suggest-areas", tags=["Onboarding", "AI Suggestions", "GPT-4o"])
async def suggest_areas(user_id: str = Query(...), occupation: str = Query(...)):
    """
    Step 2: GPT-4o로 영역 추천

    Tags:
    - Onboarding (대분류): 온보딩 기능
    - AI Suggestions (중분류): AI 추천
    - GPT-4o (소분류): GPT-4o 기반

    Features:
    - GPT-4o로 직업별 관심 영역 추천
    - 3-5개 영역 자동 생성

    Example:
        GET /onboarding/suggest-areas?user_id=user_123&occupation=교사

    Returns:
        {
            "status": "success",
            "user_id": "user_123",
            "suggested_areas": ["학생지도", "커리큘럼", ...]
        }
    """
    try:
        logger.info(f"[SuggestAreas] user_id: {user_id}, occupation: {occupation}")

        # GPT-4o 영역 추천
        result = gpt_helper.suggest_areas(occupation)

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        suggested_areas = result.get("areas", [])
        logger.info(f"[SuggestAreas] GPT-4o suggested areas: {suggested_areas}")

        return {
            "status": "success",
            "user_id": user_id,
            "occupation": occupation,
            "suggested_areas": suggested_areas,
            "message": "Step 2: 아래 영역 중 관심있는 것을 선택하세요",
            "next_step": "/onboarding/save-context (POST with selected_areas)",
        }

    except Exception as e:
        logger.error(f"[SuggestAreas] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"영역 추천 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 3: 영역 선택 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/save-context", tags=["Onboarding", "User Setup", "Save Context"])
async def save_context(input_data: Step2Input):
    """
    Step 3: 사용자 영역 선택 저장

    Tags:
    - Onboarding (대분류): 온보딩 기능
    - User Setup (중분류): 사용자 설정
    - Save Context (소분류): 컨텍스트 저장

    Features:
    - users_profiles.csv 업데이트 (areas 채우기)
    - user_context_mapping.json에 저장

    Example:
        POST /onboarding/save-context
        {
            "user_id": "user_123",
            "selected_areas": ["학생지도", "커리큘럼관리"]
        }

    Returns:
        {
            "status": "success",
            "message": "🎉 온보딩 완료!"
        }
    """
    try:
        logger.info(
            f"[SaveContext] user_id: {input_data.user_id}, areas: {input_data.selected_areas}"
        )

        # 1. users_profiles.csv 업데이트 (areas 채우기)
        data_manager.update_user_areas(
            user_id=input_data.user_id, areas=",".join(input_data.selected_areas)
        )

        # 2. user_context_mapping.json에 저장
        result = data_manager.save_user_context(
            user_id=input_data.user_id, areas=input_data.selected_areas
        )

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))

        return {
            "status": "success",
            "user_id": input_data.user_id,
            "selected_areas": input_data.selected_areas,
            "message": "🎉 온보딩 완료! 이제 분류를 시작하세요",
            "next_step": f"/classifier/classify?user_id={input_data.user_id}",
        }

    except Exception as e:
        logger.error(f"[SaveContext] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"컨텍스트 저장 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 4: 온보딩 상태 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get(
    "/status/{user_id}", response_model=dict, tags=["Onboarding", "Status", "Query"]
)
async def get_onboarding_status(user_id: str):
    """
    Step 4: 온보딩 상태 확인

    Tags:
    - Onboarding (대분류): 온보딩 기능
    - Status (중분류): 상태 조회
    - Query (소분류): 조회

    Features:
    - 사용자 프로필 조회
    - 온보딩 완료 여부 확인

    Example:
        GET /onboarding/status/user_123

    Returns:
        {
            "user_id": "user_123",
            "is_completed": true,
            "areas": ["학생지도", "커리큘럼"]
        }
    """
    try:
        user_data = data_manager.get_user_profile(user_id)

        if not user_data:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

        is_completed = bool(user_data.get("areas"))

        return {
            "status": "success",
            "user_id": user_id,
            "occupation": user_data.get("occupation"),
            "areas": (
                user_data.get("areas", "").split(",") if user_data.get("areas") else []
            ),
            "is_completed": is_completed,
            "message": "온보딩 완료됨" if is_completed else "온보딩 진행 중...",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 조회 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 5: 추가 온보딩 단계 (선택)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/step2", tags=["Onboarding", "Optional", "Keywords"])
async def onboarding_step2(user_id: str = Query(...), keywords: str = Query(...)):
    """
    메타데이터 (키워드) 저장 (선택 사항)

    Tags:
    - Onboarding (대분류): 온보딩 기능
    - Optional (중분류): 선택 단계
    - Keywords (소분류): 키워드 설정
    """
    try:
        keyword_list = keywords.split(",")
        # TODO: 데이터베이스에 저장
        return {"status": "success", "user_id": user_id, "keywords": keyword_list}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/step3", tags=["Onboarding", "Optional", "Goals"])
async def onboarding_step3(user_id: str, goals: str):
    """
    Step 3: 목표 저장 (선택 사항)

    Tags:
    - Onboarding (대분류): 온보딩 기능
    - Optional (중분류): 선택 단계
    - Goals (소분류): 목표 설정
    """
    try:
        # 구현
        return {"status": "success"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/step4", tags=["Onboarding", "Optional", "Areas"])
async def onboarding_step4(user_id: str, areas: str):
    """
    Step 4: 영역 저장 (선택 사항)

    Tags:
    - Onboarding (대분류): 온보딩 기능
    - Optional (중분류): 선택 단계
    - Areas (소분류): 영역 설정
    """
    try:
        # 구현
        return {"status": "success"}

    except Exception as e:
        return {"status": "error", "message": str(e)}

# backend/routes/onboarding_routes.py

"""
🚀 온보딩 API 라우트
사용자 프로필 수집 → 영역 추천 → 맥락 저장
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
import uuid
import json
import os
from backend.data_manager import DataManager
from backend.classifier.context_injector import get_context_injector 

router = APIRouter(tags=["onboarding"]) 
#router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
data_manager = DataManager()

# =====================
# 📋 요청/응답 모델
# =====================

class Step1Input(BaseModel):
    """Step 1: 사용자 직업 입력"""
    occupation: str
    name: str = "Anonymous"

class Step2Input(BaseModel):
    """Step 2: 영역 선택"""
    user_id: str
    selected_areas: list[str]

class OnboardingStatus(BaseModel):
    """온보딩 상태"""
    user_id: str
    occupation: str
    areas: list[str]
    is_completed: bool

# =====================
# 🚀 API 엔드포인트
# =====================

@router.post("/step1", response_model=dict)
async def onboarding_step1(input_data: Step1Input):
    """
    📍 Step 1: 사용자 직업 입력
    
    입력: {"occupation": "교사", "name": "Jay"}
    출력: {"user_id": "user_...", "message": "Step 1 완료"}
    """
    try:
        # 1️⃣ user_id 자동 생성
        user_id = f"user_{str(uuid.uuid4())[:8]}"
        
        # 2️⃣ users_profiles.csv에 저장 (areas는 아직 빈 상태)
        data_manager.save_user_profile(
            user_id=user_id,
            occupation=input_data.occupation,
            areas="",  # 아직 선택 안 함
            interests=""
        )
        
        return {
            "status": "success",
            "user_id": user_id,
            "occupation": input_data.occupation,
            "message": "Step 1 완료! 이제 영역을 추천받으세요",
            "next_step": "/api/onboarding/suggest-areas?user_id={user_id}&occupation={occupation}".format(
                user_id=user_id,
                occupation=input_data.occupation
            )
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Step 1 실패: {str(e)}")


@router.get("/suggest-areas")
async def suggest_areas(user_id: str, occupation: str):
    """
    🎯 Step 2: GPT로 영역 추천
    
    입력: ?user_id=user_123&occupation=교사
    출력: {"user_id": "user_123", "areas": ["학생지도", "커리큘럼", ...]}
    
    실제 구현: GPT API 호출
    TEST: 하드코딩된 추천값 사용
    """
    try:
        # 🧪 TEST용 추천값 (나중에 GPT로 변경)
        occupation_suggestions = {
            "교사": ["학생지도", "커리큘럼관리", "교사협력", "학생평가", "수업계획"],
            "개발자": ["코드리뷰", "아키텍처설계", "팀협업", "기술학습", "프로젝트관리"],
            "마케터": ["캠페인전략", "고객분석", "브랜드관리", "데이터분석", "시장조사"],
            "학생": ["시험준비", "과제관리", "동아리활동", "진로탐색", "공부습관"],
        }
        
        suggested_areas = occupation_suggestions.get(
            occupation, 
            ["관심분야1", "관심분야2", "관심분야3", "관심분야4", "관심분야5"]
        )
        
        return {
            "status": "success",
            "user_id": user_id,
            "occupation": occupation,
            "suggested_areas": suggested_areas,
            "message": "Step 2: 아래 영역 중 관심있는 것을 선택하세요",
            "next_step": f"/api/onboarding/save-context (POST with selected_areas)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"영역 추천 실패: {str(e)}")


@router.post("/save-context")
async def save_context(input_data: Step2Input):
    """
    💾 Step 3: 사용자 영역 선택 저장
    
    입력: {
        "user_id": "user_123",
        "selected_areas": ["학생지도", "커리큘럼관리"]
    }
    출력: {"status": "success", "message": "온보딩 완료!"}
    """
    try:
        # 1️⃣ users_profiles.csv 업데이트 (areas 채우기)
        data_manager.update_user_areas(
            user_id=input_data.user_id,
            areas=",".join(input_data.selected_areas)
        )
        
        # 2️⃣ user_context_mapping.json에 저장
        data_manager.save_user_context(
            user_id=input_data.user_id,
            areas=input_data.selected_areas
        )

        # ✅ 이 줄은 지워도 돼! (지금은 안 필요)
        # injector = get_context_injector()
        # (분류할 때 사용)
        # injector.inject_context_to_prompt(
        #     base_prompt=input_data.base_prompt,
        #     user_id=input_data.user_id
        # )
        
        return {
            "status": "success",
            "user_id": input_data.user_id,
            "selected_areas": input_data.selected_areas,
            "message": "🎉 온보딩 완료! 이제 분류를 시작하세요",
            "next_step": f"/api/classify?user_id={input_data.user_id}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"컨텍스트 저장 실패: {str(e)}")


@router.get("/status/{user_id}", response_model=dict)
async def get_onboarding_status(user_id: str):
    """
    ✅ Step 4: 온보딩 상태 확인
    
    입력: /api/onboarding/status/user_123
    출력: {"user_id": "user_123", "is_completed": true, ...}
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
            "areas": user_data.get("areas", "").split(",") if user_data.get("areas") else [],
            "is_completed": is_completed,
            "message": "온보딩 완료됨" if is_completed else "온보딩 진행 중..."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"상태 조회 실패: {str(e)}")


@router.post("/step2")
async def onboarding_step2(
    user_id: str = Query(...),      # ← Query(...) 명시!
    keywords: str = Query(...)      # ← Query(...) 명시!
):
    """
    메타데이터 (키워드) 저장
    """
    try:
        keyword_list = keywords.split(",")
        # TODO: 데이터베이스에 저장
        return {
            "status": "success",
            "user_id": user_id,
            "keywords": keyword_list
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/step3")
async def onboarding_step3(user_id: str, goals: str):
    """Step 3: 목표 저장"""
    try:
        # 구현
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/step4")
async def onboarding_step4(user_id: str, areas: str):
    """Step 4: 영역 저장"""
    try:
        # 구현
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}



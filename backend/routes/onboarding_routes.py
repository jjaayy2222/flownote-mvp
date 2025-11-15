# backend/routes/onboarding_routes.py

"""
🚀 Onboarding 라우트: GPT-4o 연동
- Step 1: occupation 기반 영역 추천 (GPT-4o 사용)
- Save Context: 선택된 영역 저장 (간소화)
"""

import uuid
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime
from typing import List
import json
import os
from backend.data_manager import DataManager
from backend.classifier.context_injector import get_context_injector 
from backend.services.gpt_helper import get_gpt_helper      # 싱클톤 함수 호출
from backend.services.gpt_helper import GPT4oHelper         # 클래스 호출

# API Router
router = APIRouter(tags=["onboarding"])  

# 인스턴스 생성
data_manager = DataManager()
gpt_helper = get_gpt_helper()           # 싱글톤

logger = logging.getLogger(__name__)


# =====================================
# 📌 Pydantic Models (요청/응답 모델)
# =====================================

class Step1Input(BaseModel):
    """Step 1 요청 모델: 사용자 직업 입력"""
    occupation: str             # 직업
    name: str = "Anonymous"     # 이름 (기본값: Anonymous)


class Step2Input(BaseModel):
    """Step 2: 영역 선택"""
    user_id: str
    selected_areas: List[str]


class OnboardingStatus(BaseModel):
    """온보딩 상태"""
    user_id: str
    #name: str
    occupation: str
    areas: List[str]
    #projects: List[str]
    is_completed: bool

# =====================
# 🚀 API 엔드포인트
# =====================

# =====================================
# 📌 Step 1: 직업 입력 → GPT-4o 영역 추천
# =====================================

@router.post("/step1", response_model=dict)
async def onboarding_step1(input_data: Step1Input):
    """
    📍 Step 1: 사용자 직업 입력
    
    입력: {"occupation": "교사", "name": "Jay"}
    출력: {"user_id": "user_...", "message": "Step 1 완료"}
    """
    try:
        # 1. user_id 자동 생성
        user_id = f"user_{str(uuid.uuid4())[:8]}"
        logger.info(f"[Step1] Generated user_id: {user_id}, occupation: {input_data.occupation}")
        
        # 2.users_profiles.csv에 저장 (areas는 아직 빈 상태)
        data_manager.save_user_profile(
            user_id=user_id,
            occupation=input_data.occupation,
            areas="",               # 아직 선택 안 함
            interests=""
        )
        
        return {
            "status": "success",
            "user_id": user_id,
            "occupation": input_data.occupation,
            "message": "Step 1 완료! 이제 영역을 추천받으세요",
            "next_step": f"/api/onboarding/suggest-areas?user_id={user_id}&occupation={input_data.occupation}"
        }
    
    except Exception as e:
        logger.error(f"[Step1] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Step 1 실패: {str(e)}")


# ==============================================
# 📌 GET /suggest-areas: GPT-4o 영역 추천 (테스트용)
# ==============================================

@router.get("/suggest-areas")
async def suggest_areas(user_id: str = Query(...), occupation: str = Query(...)):
    """
    🎯 Step 2: GPT-4o로 영역 추천
    
    입력: ?user_id=user_123&occupation=교사
    출력: {"user_id": "user_123", "areas": ["학생지도", "커리큘럼", ...]}
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
            "next_step": "/api/onboarding/save-context (POST with selected_areas)"
        }
    
    except Exception as e:
        logger.error(f"[SuggestAreas] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"영역 추천 실패: {str(e)}")


# =====================================
# 📌 Step 2: 영역 선택 저장 
# =====================================

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
        logger.info(f"[SaveContext] user_id: {input_data.user_id}, areas: {input_data.selected_areas}")
        
        # 1. users_profiles.csv 업데이트 (areas 채우기)
        data_manager.update_user_areas(
            user_id=input_data.user_id,
            areas=",".join(input_data.selected_areas)
        )
        
        # 2. user_context_mapping.json에 저장
        result = data_manager.save_user_context(
            user_id=input_data.user_id,
            areas=input_data.selected_areas
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message"))
        
        return {
            "status": "success",
            "user_id": input_data.user_id,
            "selected_areas": input_data.selected_areas,
            "message": "🎉 온보딩 완료! 이제 분류를 시작하세요",
            "next_step": f"/api/classify?user_id={input_data.user_id}"
        }
    
    except Exception as e:
        logger.error(f"[SaveContext] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"컨텍스트 저장 실패: {str(e)}")

# ==============================================
# 📌 GET /status/{user_id}: 온보딩 상태 확인
# ==============================================

@router.get("/status/{user_id}", response_model=dict)
async def get_onboarding_status(user_id: str):
    """
    Step 4: 온보딩 상태 확인
    
    - 입력: /api/onboarding/status/user_123
    - 출력: {"user_id": "user_123", "is_completed": true, ...}
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


# backend/routes/onboarding_routes.py

from fastapi import FastAPI
from data_manager import DataManager

app = FastAPI()
dm = DataManager()

@app.post("/api/onboarding/save")
async def save_onboarding(user_id: str, occupation: str, 
                        areas: list, interests: list):
    """온보딩 데이터 저장"""
    profile_saved = dm.save_user_profile(user_id, occupation, areas, interests)
    
    if profile_saved:
        return {"status": "success", "user_id": user_id}
    else:
        return {"status": "error"}, 500

@app.get("/api/user/{user_id}/profile")
async def get_profile(user_id: str):
    """사용자 프로필 조회"""
    profile = dm.get_user_profile(user_id)
    if profile:
        return profile
    else:
        return {"status": "error"}, 404

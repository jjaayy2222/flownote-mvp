# backend/main.py

"""
FastAPI 메인 서버
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
from datetime import datetime
import uuid

# 현재 구조 그대로 import
from backend.routes.api_routes import router
from backend.routes.classifier_routes import router as classifier_router
from backend.routes.onboarding_routes import router as onboarding_router
from backend.metadata import FileMetadata


# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI 앱 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app = FastAPI(
    title="FlowNote API",
    description="PARA Classification + Conflict Resolution API",
    version="3.0.0"
)

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    #allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # 명시적으로
    # allow_origins=["http://localhost:3000"],  # React
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 라우터 등록 (각각 따로!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ✅ 라우터 등록 (prefix 없이!!)
app.include_router(router)
logger.info("✅ api_router 등록 완료")

#app.include_router(classifier_router, prefix="/api/classify") 
app.include_router(classifier_router, prefix="/api/classifier")
logger.info("✅ classifier_router 등록 완료")

app.include_router(onboarding_router, prefix="/api/onboarding")
logger.info("✅ onboarding_router 등록 완료")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 요청 모델
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HealthCheckResponse(BaseModel):
    status: str
    timestamp: str

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬스체크
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/health")
async def health():
    """서버 상태 확인"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "FlowNote API v3.0.0",
        "docs": "/docs",
        "health": "/health"
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 FlowNote API 시작...")
    logger.info("📍 http://localhost:8000")
    logger.info("📚 문서: http://localhost:8000/docs")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )



#
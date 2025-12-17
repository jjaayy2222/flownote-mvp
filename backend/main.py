# backend/main.py

"""
FastAPI 메인 서버
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
from datetime import datetime, timezone
import uuid

# 마이그레이션 모델 임포트
from backend.models import HealthCheckResponse, FileMetadata

from backend.routes.conflict_routes import router as conflict_router
from backend.routes.classifier_routes import router as classifier_router
from backend.routes.onboarding_routes import router as onboarding_router
from backend.api.endpoints.sync import router as sync_router
from backend.api.endpoints.automation import router as automation_router


# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI 앱 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

app = FastAPI(
    title="FlowNote API",
    description="""
    ## FlowNote MVP - AI 기반 PARA 분류 및 충돌 해결 API
    
    ### 주요 기능
    * **온보딩**: 사용자 생성 및 관심 영역 추천
    * **분류**: PARA 방법론 기반 텍스트 자동 분류
    * **충돌 해결**: AI 기반 분류 충돌 감지 및 해결
    
    ### 엔드포인트
    * `/classifier` - 파일 및 텍스트 분류
    * `/onboarding` - 사용자 온보딩
    * `/conflict` - 충돌 해결
    * `/health` - 서버 상태 확인
    
    ### 테스트 커버리지
    * 전체 커버리지: 51%
    * 핵심 서비스: 70%+
    
    ### CI/CD
    * GitHub Actions 자동 테스트
    * Codecov 커버리지 리포팅
    """,
    version="4.0.0",
    contact={
        "name": "FlowNote Team",
        "url": "https://github.com/jjaayy2222/flownote-mvp",
        "email": "your-email@example.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    # allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # 명시적으로
    # allow_origins=["http://localhost:3000"],  # React
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 라우터 등록
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 라우터 등록
logger.info("✅ 기본_router 등록 완료")

# classifier_router
app.include_router(classifier_router, prefix="/classifier", tags=["classifier"])
logger.info("✅ classifier_router 등록 완료")

# onboarding_router
app.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
logger.info("✅ onboarding_router 등록 완료")

# conflict_router
app.include_router(conflict_router, prefix="/conflict", tags=["conflict"])
logger.info("✅ conflict_router 등록 완료 (resolve 전용)")

# sync_router (Phase 3: MCP Integration)
app.include_router(sync_router)
logger.info("✅ sync_router 등록 완료 (MCP Sync & Conflict Resolution)")

# automation_router (Phase 4: Celery Automation)


app.include_router(automation_router, prefix="/api")
logger.info("✅ automation_router 등록 완료 (Celery Automation)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Health Check & Root
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/health", response_model=HealthCheckResponse, tags=["System"])
async def health():
    """
    서버 상태 확인

    Returns:
        HealthCheckResponse: 서버 상태 정보
    """
    return HealthCheckResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="4.0.0",
    )


@app.get("/", tags=["System"])
async def root():
    """
    루트 엔드포인트

    Returns:
        dict: API 정보
    """
    return {
        "name": "FlowNote API",
        "version": "4.0.0",
        "docs": "/docs",
        "health": "/health",
        "routes": {
            "classification": "/classify",
            "conflict": "/conflicts",
            "onboarding": "/onboarding",
        },
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
        # app,
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        # log_level="info",
        reload=True,
    )

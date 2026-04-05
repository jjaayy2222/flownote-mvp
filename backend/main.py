# backend/main.py

"""
FastAPI 메인 서버
"""

from fastapi import FastAPI, UploadFile, File, HTTPException  # type: ignore[import]
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[import]
from pydantic import BaseModel  # type: ignore[import]
import logging
from datetime import datetime, timezone
import uuid

from contextlib import asynccontextmanager
from backend.services.websocket_manager import manager  # type: ignore[import]
from backend.api.endpoints.websocket import router as websocket_router  # type: ignore[import]

# 마이그레이션 모델 임포트
from backend.models import HealthCheckResponse, FileMetadata  # type: ignore[import]

from backend.routes.conflict_routes import router as conflict_router  # type: ignore[import]
from backend.routes.classifier_routes import router as classifier_router  # type: ignore[import]
from backend.routes.onboarding_routes import router as onboarding_router  # type: ignore[import]
from backend.api.endpoints.sync import router as sync_router  # type: ignore[import]
from backend.api.endpoints.automation import router as automation_router  # type: ignore[import]
from backend.api.endpoints.graph import router as graph_router  # type: ignore[import]
from backend.api.endpoints.search import router as search_router  # type: ignore[import]
from backend.api.endpoints.chat import router as chat_router  # type: ignore[import]


# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Discord 알림 핸들러 활성화
from backend.utils.observability import DiscordAlertHandler
logging.getLogger().addHandler(DiscordAlertHandler())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI 앱 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


from backend.services.scheduler_service import start_scheduler, shutdown_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up: Initializing WebSocket Manager & Redis...")
    await manager.initialize()
    
    # 스케줄러(Golden Dataset 수집 등) 시작
    start_scheduler()
    
    yield
    
    # Shutdown
    logger.info("Shutting down: Cleaning up resources...")
    shutdown_scheduler()
    await manager.shutdown()


app = FastAPI(
    lifespan=lifespan,
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
    * `/search/hybrid` - FAISS+BM25 하이브리드 RAG 검색 (PARA 카테고리 필터 지원)
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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Exception Handlers (i18n support)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from fastapi.exceptions import RequestValidationError  # type: ignore[import]
from fastapi import Request  # type: ignore[import]
from fastapi.responses import JSONResponse  # type: ignore[import]
from backend.api.exceptions import http_exception_handler, validation_exception_handler  # type: ignore[import]
from backend.services.chat_history_service import RedisUnavailableError  # type: ignore[import]

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.exception_handler(RedisUnavailableError)
async def redis_unavailable_handler(request: Request, exc: RedisUnavailableError) -> JSONResponse:
    """Redis 연결 불가 시 전역 503 응답 반환.

    chat_history_service의 모든 엔드포인트에서 각자 RedisUnavailableError를
    처리하지 않아도 이 핸들러가 자동으로 503으로 변환한다.
    """
    logger.warning(
        "Redis unavailable: %s",
        str(exc),
        extra={"path": request.url.path},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Redis unavailable. Please try again later."},
    )


logger.info("✅ 전역 예외 처리기 등록 완료 (i18n 지원 + Redis 503)")


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

# websocket_router (Phase 1: Real-time Updates)
app.include_router(websocket_router)
logger.info("✅ sync_router 등록 완료 (MCP Sync & Conflict Resolution)")

# search_router (Phase 2-②: RAG API Integration)
app.include_router(search_router)
logger.info("✅ search_router 등록 완료 (Hybrid RAG Search)")

# automation_router (Phase 4: Celery Automation)


app.include_router(automation_router, prefix="/api")
logger.info("✅ automation_router 등록 완료 (Celery Automation)")

app.include_router(graph_router, prefix="/api")
logger.info("✅ graph_router 등록 완료 (Visualization)")

# chat_router (Issue #614: RAG 스트리밍 채팅)
app.include_router(chat_router, prefix="/api")
logger.info("✅ chat_router 등록 완료 (RAG Streaming Chat)")


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
    import uvicorn  # type: ignore[import]

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

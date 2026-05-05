# backend/api/routes.py

"""Main API Router"""

from fastapi import APIRouter, Depends
from . import endpoints
from .deps import get_locale
from .models import HealthCheckResponse
from ..services.i18n_service import get_message

router = APIRouter(prefix="/api")


# Health check endpoint
@router.get("/health", response_model=HealthCheckResponse)
async def health_check(locale: str = Depends(get_locale)) -> HealthCheckResponse:
    """서버 상태 확인 (다국어 지원)"""
    return HealthCheckResponse(status="ok", message=get_message("status_ok", locale))


# Include endpoint routers
router.include_router(endpoints.classify_router)
router.include_router(endpoints.search_router)
router.include_router(endpoints.metadata_router)
router.include_router(endpoints.chat_router)
router.include_router(endpoints.admin_router)

# GDPR Right-to-Erasure 엔드포인트 (Phase 2-4)
# schedule_audit_log_cleanup()은 FastAPI lifespan 또는 Celery Beat에서 등록 필요
# 참조: backend.core.audit_logger.schedule_audit_log_cleanup
router.include_router(endpoints.privacy_router)

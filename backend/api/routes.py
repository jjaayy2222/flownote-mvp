# backend/api/routes.py

"""Main API Router"""

from fastapi import APIRouter, Depends
from . import endpoints
from .deps import get_locale
from ..services.i18n_service import get_message

router = APIRouter(prefix="/api")


# Health check endpoint
@router.get("/health")
async def health_check(locale: str = Depends(get_locale)):
    """서버 상태 확인 (다국어 지원)"""
    return {"status": "ok", "message": get_message("status_ok", locale)}


# Include endpoint routers
router.include_router(endpoints.classify_router)
router.include_router(endpoints.search_router)
router.include_router(endpoints.metadata_router)

# backend/api/routes.py

"""Main API Router"""

from fastapi import APIRouter
from . import endpoints

router = APIRouter(prefix="/api")

# Include endpoint routers
router.include_router(endpoints.classify_router)
router.include_router(endpoints.search_router)
router.include_router(endpoints.metadata_router)
# backend/api/endpoints/search.py

"""Search Endpoint"""

from fastapi import APIRouter, Depends
from ...api.deps import get_locale
from ...services.i18n_service import get_message

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/")
async def search_files(q: str, locale: str = Depends(get_locale)):
    """검색 엔드포인트 (다국어 지원)"""
    results = []  # TODO: Implement actual search logic
    return {
        "query": q,
        "message": get_message("search_results", locale, count=len(results)),
        "results": results,
    }

# backend/api/endpoints/search.py

"""Search Endpoint"""

from fastapi import APIRouter

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/")
async def search_files(q: str):
    """검색 엔드포인트"""
    return {"query": q, "results": []}
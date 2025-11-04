# backend/api/endpoints/metadata.py

"""Metadata Endpoint"""

from fastapi import APIRouter

router = APIRouter(prefix="/metadata", tags=["metadata"])

@router.get("/{file_id}")
async def get_metadata(file_id: str):
    """메타데이터 조회"""
    return {"file_id": file_id, "metadata": {}}
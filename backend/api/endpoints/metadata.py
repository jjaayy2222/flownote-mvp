# backend/api/endpoints/metadata.py

"""Metadata Endpoint"""

from fastapi import APIRouter, Depends
from ...api.deps import get_locale
from ...services.i18n_service import get_message

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/{file_id}")
async def get_metadata(file_id: str, locale: str = Depends(get_locale)):
    """메타데이터 조회 (다국어 지원)"""
    # TODO: Implement actual metadata retrieval
    metadata = {}
    return {"file_id": file_id, "metadata": metadata}


@router.put("/{file_id}")
async def update_metadata(file_id: str, locale: str = Depends(get_locale)):
    """메타데이터 업데이트 (다국어 지원)"""
    # TODO: Implement actual metadata update
    return {"file_id": file_id, "message": get_message("metadata_updated", locale)}

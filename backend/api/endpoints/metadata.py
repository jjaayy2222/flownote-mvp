# backend/api/endpoints/metadata.py

"""Metadata Endpoint"""

from fastapi import APIRouter, Depends
from ...api.deps import get_locale
from ...api.models import MetadataResponse
from ...services.i18n_service import get_message

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/{file_id}", response_model=MetadataResponse)
async def get_metadata(
    file_id: str, locale: str = Depends(get_locale)
) -> MetadataResponse:
    """메타데이터 조회 (다국어 지원)"""
    # TODO: Implement actual metadata retrieval
    metadata = {}
    return MetadataResponse(
        status="success",
        message=get_message("metadata_fetched", locale),
        file_id=file_id,
        metadata=metadata,
    )


@router.put("/{file_id}", response_model=MetadataResponse)
async def update_metadata(
    file_id: str, locale: str = Depends(get_locale)
) -> MetadataResponse:
    """메타데이터 업데이트 (다국어 지원)"""
    # TODO: Implement actual metadata update
    metadata = {}
    return MetadataResponse(
        status="success",
        message=get_message("metadata_updated", locale),
        file_id=file_id,
        metadata=metadata,
    )

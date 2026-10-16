# backend/api/endpoints/metadata.py

"""
Metadata Endpoint
파일 메타데이터 조회 및 부분 업데이트 API
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.agent.error_utils import log_agent_error
from backend.api.deps import get_locale
from backend.api.models import MetadataResponse, MetadataUpdateRequest
from backend.metadata import get_file_metadata
from backend.services.i18n_service import get_message
from backend.utils.common import mask_pii_id

router = APIRouter(prefix="/metadata", tags=["metadata"])
logger = logging.getLogger(__name__)


@router.get("/{file_id}", response_model=MetadataResponse)
async def get_metadata(
    file_id: str,
    locale: str = Depends(get_locale),
) -> MetadataResponse:
    """메타데이터 조회 (다국어 지원)

    - file_id로 영속화된 파일 메타데이터 레코드 조회
    - 대상 파일 부재 시 404 오류 반환
    """
    effective_file_id = (file_id and file_id.strip()) or ""
    if not effective_file_id:
        raise HTTPException(
            status_code=400,
            detail="file_id는 필수 입력값입니다.",
        )

    try:
        metadata_mgr = get_file_metadata()
        record = metadata_mgr.get_file(effective_file_id)

        if record is None:
            masked_id = mask_pii_id(effective_file_id)
            logger.info(
                "[METADATA] File metadata not found",
                extra={"file_id_hash": masked_id},
            )
            raise HTTPException(
                status_code=404,
                detail=get_message("metadata_not_found", locale, file_id=masked_id),
            )

        return MetadataResponse(
            status="success",
            message=get_message("metadata_fetched", locale),
            file_id=effective_file_id,
            metadata=dict(record),
        )
    except HTTPException:
        raise
    except Exception as exc:
        log_agent_error(
            logger,
            "Failed to retrieve file metadata",
            exc,
            extra_metadata={
                "file_id_hash": mask_pii_id(effective_file_id),
                "error_type": type(exc).__name__,
            },
            include_traceback=True,
        )
        raise HTTPException(
            status_code=500,
            detail="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from exc


@router.put("/{file_id}", response_model=MetadataResponse)
async def update_metadata(
    file_id: str,
    body: MetadataUpdateRequest,
    locale: str = Depends(get_locale),
) -> MetadataResponse:
    """메타데이터 업데이트 (다국어 지원)

    - file_id에 해당하는 파일 메타데이터 필드 부분 갱신
    - 대상 파일 부재 시 404 오류 반환
    - 영속화 실패 시 롤백 및 500 오류 반환
    """
    effective_file_id = (file_id and file_id.strip()) or ""
    if not effective_file_id:
        raise HTTPException(
            status_code=400,
            detail="file_id는 필수 입력값입니다.",
        )

    try:
        metadata_mgr = get_file_metadata()
        existing = metadata_mgr.get_file(effective_file_id)

        if existing is None:
            masked_id = mask_pii_id(effective_file_id)
            logger.info(
                "[METADATA] Cannot update: File metadata not found",
                extra={"file_id_hash": masked_id},
            )
            raise HTTPException(
                status_code=404,
                detail=get_message("metadata_not_found", locale, file_id=masked_id),
            )

        success = metadata_mgr.update_file(effective_file_id, body.updates)
        if not success:
            logger.error(
                "[METADATA] Persistence failed during metadata update",
                extra={"file_id_hash": mask_pii_id(effective_file_id)},
            )
            raise HTTPException(
                status_code=500,
                detail="메타데이터 저장에 실패했습니다. 잠시 후 다시 시도해주세요.",
            )

        updated_record = metadata_mgr.get_file(effective_file_id) or {}

        return MetadataResponse(
            status="success",
            message=get_message("metadata_updated", locale),
            file_id=effective_file_id,
            metadata=dict(updated_record),
        )
    except HTTPException:
        raise
    except Exception as exc:
        log_agent_error(
            logger,
            "Failed to update file metadata",
            exc,
            extra_metadata={
                "file_id_hash": mask_pii_id(effective_file_id),
                "error_type": type(exc).__name__,
            },
            include_traceback=True,
        )
        raise HTTPException(
            status_code=500,
            detail="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        ) from exc

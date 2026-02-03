# backend/api/endpoints/classify.py

"""Classification Endpoint"""

from fastapi import APIRouter, UploadFile, File, Depends
from ...api.deps import get_locale
from ...api.models import FileProcessingResponse
from ...services.i18n_service import get_message

router = APIRouter(prefix="/classify", tags=["classify"])


@router.post("/file", response_model=FileProcessingResponse)
async def classify_file(
    file: UploadFile = File(...), locale: str = Depends(get_locale)
) -> FileProcessingResponse:
    """파일 분류 엔드포인트 (다국어 지원)"""
    return FileProcessingResponse(
        status="processing",
        message=get_message("file_processing", locale, filename=file.filename),
        file=file.filename,
    )

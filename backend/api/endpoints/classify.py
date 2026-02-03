# backend/api/endpoints/classify.py

"""Classification Endpoint"""

from fastapi import APIRouter, UploadFile, File, Depends
from ...api.deps import get_locale
from ...api.models import FileProcessingResponse
from ...api.exceptions import localized_http_exception
from ...services.i18n_service import get_message
from ...core.config import settings

router = APIRouter(prefix="/classify", tags=["classify"])


@router.post("/file", response_model=FileProcessingResponse)
async def classify_file(
    file: UploadFile = File(...), locale: str = Depends(get_locale)
) -> FileProcessingResponse:
    """파일 분류 엔드포인트 (다국어 지원)"""

    # Validation: Check file size against global limit
    max_file_size = settings.MAX_UPLOAD_SIZE

    # Read file content to check size
    content = await file.read()
    if len(content) > max_file_size:
        max_size_mb = max_file_size / (1024 * 1024)
        raise localized_http_exception(
            status_code=413,
            message_key="payload_too_large",
            locale=locale,
            max_size=max_size_mb,
        )

    # Reset file pointer
    await file.seek(0)

    return FileProcessingResponse(
        status="processing",
        message=get_message("file_processing", locale, filename=file.filename),
        file=file.filename,
    )

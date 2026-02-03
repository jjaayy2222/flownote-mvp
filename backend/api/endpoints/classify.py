# backend/api/endpoints/classify.py

"""Classification Endpoint"""

from fastapi import APIRouter, UploadFile, File, Depends
from ...api.deps import get_locale
from ...api.models import FileProcessingResponse
from ...api.exceptions import localized_http_exception
from ...services.i18n_service import get_message

router = APIRouter(prefix="/classify", tags=["classify"])


@router.post("/file", response_model=FileProcessingResponse)
async def classify_file(
    file: UploadFile = File(...), locale: str = Depends(get_locale)
) -> FileProcessingResponse:
    """파일 분류 엔드포인트 (다국어 지원)"""

    # Validation example: Check file size (10MB limit)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

    # Read file content to check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise localized_http_exception(
            status_code=400, message_key="bad_request", locale=locale
        )

    # Reset file pointer
    await file.seek(0)

    return FileProcessingResponse(
        status="processing",
        message=get_message("file_processing", locale, filename=file.filename),
        file=file.filename,
    )

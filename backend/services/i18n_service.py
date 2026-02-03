# backend/services/i18n_service.py

import logging
from typing import Dict, Any

# Setup logger for i18n debugging
logger = logging.getLogger(__name__)

MESSAGES: Dict[str, Dict[str, str]] = {
    "ko": {
        "file_classified": "파일이 {category}로 분류되었습니다.",
        "sync_completed": "동기화가 완료되었습니다.",
        "conflict_detected": "충돌이 감지되었습니다.",
        "not_found": "리소스를 찾을 수 없습니다.",
        "unauthorized": "인증되지 않은 접근입니다.",
        "server_error": "서버 내부 오류가 발생했습니다.",
        # API Endpoint Messages
        "file_processing": "파일 처리 중: {filename}",
        "file_upload_success": "파일이 성공적으로 업로드되었습니다: {filename}",
        "file_upload_failed": "파일 업로드 실패: {error}",
        "status_ok": "서버가 정상 작동 중입니다",
        "search_results": "{count}개의 검색 결과를 찾았습니다",
        "metadata_updated": "메타데이터가 업데이트되었습니다",
        "metadata_fetched": "메타데이터를 조회했습니다",
        # Error Messages
        "bad_request": "잘못된 요청입니다",
        "forbidden": "접근 권한이 없습니다",
        "validation_error": "입력값 검증 실패: {detail}",
        "method_not_allowed": "허용되지 않은 메서드입니다",
        "payload_too_large": "업로드 파일 크기가 제한을 초과했습니다 (최대: {max_size}MB)",
    },
    "en": {
        "file_classified": "File classified as {category}.",
        "sync_completed": "Sync completed.",
        "conflict_detected": "Conflict detected.",
        "not_found": "Resource not found.",
        "unauthorized": "Unauthorized access.",
        "server_error": "Internal server error.",
        # API Endpoint Messages
        "file_processing": "Processing file: {filename}",
        "file_upload_success": "File uploaded successfully: {filename}",
        "file_upload_failed": "File upload failed: {error}",
        "status_ok": "Server is running",
        "search_results": "Found {count} search results",
        "metadata_updated": "Metadata updated",
        "metadata_fetched": "Metadata fetched",
        # Error Messages
        "bad_request": "Bad request",
        "forbidden": "Access forbidden",
        "validation_error": "Validation failed: {detail}",
        "method_not_allowed": "Method not allowed",
        "payload_too_large": "File size exceeds the limit (max: {max_size}MB)",
    },
}

DEFAULT_LOCALE = "ko"
SUPPORTED_LOCALES = ["ko", "en"]


def get_message(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """
    Retrieve a localized message based on the key and locale.
    Supports simple string formatting using kwargs.
    Logs a warning if formatting parameters are missing.
    """
    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE

    # Get message template
    template = MESSAGES.get(locale, MESSAGES[DEFAULT_LOCALE]).get(key)

    if not template:
        # Fallback to default locale if key missing
        template = MESSAGES[DEFAULT_LOCALE].get(key, key)

    try:
        return template.format(**kwargs)
    except (KeyError, ValueError, IndexError) as e:
        # Log the error to aid debugging without crashing the request
        logger.warning(
            f"[i18n] Failed to format message. Key: '{key}', Locale: '{locale}', "
            f"Error: {e} ({type(e).__name__}). Returning raw template."
        )
        return template

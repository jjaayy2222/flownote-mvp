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
    },
    "en": {
        "file_classified": "File classified as {category}.",
        "sync_completed": "Sync completed.",
        "conflict_detected": "Conflict detected.",
        "not_found": "Resource not found.",
        "unauthorized": "Unauthorized access.",
        "server_error": "Internal server error.",
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
    except KeyError as e:
        # Log the error to aid debugging without crashing the request
        logger.warning(
            f"[i18n] Failed to format message. Key: '{key}', Locale: '{locale}', "
            f"Error: Missing placeholder {e}. Returning raw template."
        )
        return template

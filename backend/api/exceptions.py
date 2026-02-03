# backend/api/exceptions.py

"""
Custom exception handlers and utilities for i18n error responses
"""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from ..services.i18n_service import get_message, DEFAULT_LOCALE


def localized_http_exception(
    status_code: int, message_key: str, locale: str = DEFAULT_LOCALE, **kwargs
) -> HTTPException:
    """
    HTTPException을 생성하되, 로케일에 맞는 에러 메시지를 사용합니다.

    Args:
        status_code: HTTP 상태 코드
        message_key: i18n 메시지 키
        locale: 로케일 (기본값: DEFAULT_LOCALE)
        **kwargs: 메시지 포맷팅에 사용될 추가 인자

    Returns:
        HTTPException 인스턴스

    Example:
        raise localized_http_exception(404, "not_found", locale="ko")
    """
    detail = get_message(message_key, locale, **kwargs)
    return HTTPException(status_code=status_code, detail=detail)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    전역 HTTPException 핸들러 (다국어 지원)

    Accept-Language 헤더를 기반으로 에러 메시지를 현지화합니다.
    """
    from .deps import get_locale

    # Extract locale from request headers
    accept_language = request.headers.get("Accept-Language")
    locale = DEFAULT_LOCALE

    # Simple locale extraction (reuse logic from deps.py would be better)
    if accept_language:
        try:
            # Use the get_locale dependency logic
            from .deps import _parse_language_entry, SUPPORTED_LOCALES

            for part in accept_language.split(","):
                entry = _parse_language_entry(part)
                if entry and entry.primary_tag in SUPPORTED_LOCALES:
                    locale = entry.primary_tag
                    break
        except Exception:
            pass  # Fallback to default locale

    # Map status codes to message keys
    status_to_key = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        422: "validation_error",
        500: "server_error",
    }

    message_key = status_to_key.get(exc.status_code)

    # If we have a predefined message key, use it; otherwise use the original detail
    if message_key:
        detail = get_message(message_key, locale, detail=str(exc.detail))
    else:
        detail = exc.detail

    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": detail, "status_code": exc.status_code},
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Pydantic 검증 오류 핸들러 (다국어 지원)
    """
    from fastapi.exceptions import RequestValidationError

    if not isinstance(exc, RequestValidationError):
        raise exc

    # Extract locale
    accept_language = request.headers.get("Accept-Language")
    locale = DEFAULT_LOCALE

    if accept_language:
        try:
            from .deps import _parse_language_entry, SUPPORTED_LOCALES

            for part in accept_language.split(","):
                entry = _parse_language_entry(part)
                if entry and entry.primary_tag in SUPPORTED_LOCALES:
                    locale = entry.primary_tag
                    break
        except Exception:
            pass

    # Format validation errors
    errors = exc.errors()
    error_details = "; ".join([f"{err['loc'][-1]}: {err['msg']}" for err in errors])

    message = get_message("validation_error", locale, detail=error_details)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"status": "error", "message": message, "errors": errors},
    )

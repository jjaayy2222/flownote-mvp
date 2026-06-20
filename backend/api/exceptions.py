# backend/api/exceptions.py

"""
Custom exception handlers and utilities for i18n (국제화) error responses.

이 모듈은 FastAPI 애플리케이션의 전역 예외 처리를 담당합니다.
Accept-Language 헤더를 기반으로 HTTP 에러 메시지를 현지화하며,
일관된 JSON 에러 응답 구조({status, message, status_code})를 보장합니다.

Registration:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
"""

from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from backend.core.config import settings

from ..services.i18n_service import get_message


def localized_http_exception(
    status_code: int, message_key: str, locale: Optional[str] = None, **kwargs
) -> HTTPException:
    """
    지정된 HTTP 상태 코드와 i18n 메시지 키를 바탕으로 현지화된 HTTPException을 생성합니다.

    라우터나 서비스 계층에서 예외를 raise할 때 직접 HTTPException을 생성하는 대신
    이 함수를 사용하면 다국어 메시지가 자동으로 적용됩니다.
    locale이 지원되지 않거나 None인 경우, settings.DEFAULT_LOCALE로 폴백합니다.

    Args:
        status_code (int): 반환할 HTTP 상태 코드 (예: 400, 401, 404, 500).
        message_key (str): i18n 메시지 딕셔너리에서 조회할 키
                           (예: ``"not_found"``, ``"unauthorized"``).
        locale (Optional[str]): 응답 언어 코드 (예: ``"ko"``, ``"en"``).
                                None이면 ``settings.DEFAULT_LOCALE``을 사용합니다.
        **kwargs: ``get_message()`` 호출 시 메시지 템플릿에 삽입할 추가 포맷 인자.

    Returns:
        HTTPException: FastAPI가 자동으로 처리하는 HTTP 예외 인스턴스.
                       ``detail`` 필드에 현지화된 메시지가 포함됩니다.

    Raises:
        이 함수 자체는 예외를 발생시키지 않습니다. 반환된 객체를 ``raise``해야 합니다.

    Example:
        >>> # 라우터에서 사용 예시
        >>> raise localized_http_exception(
        ...     status_code=404,
        ...     message_key="not_found",
        ...     locale="ko",
        ... )
    """
    from .deps import normalize_locale

    locale = normalize_locale(locale)

    if not locale or locale not in settings.SUPPORTED_LOCALES:
        locale = settings.DEFAULT_LOCALE

    detail = get_message(message_key, locale, **kwargs)
    return HTTPException(status_code=status_code, detail=detail)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    FastAPI 전역 HTTPException 핸들러 (다국어 지원).

    ``app.add_exception_handler(HTTPException, http_exception_handler)``로 등록하여
    앱 전체에서 발생하는 HTTPException을 일관된 JSON 형식으로 처리합니다.
    요청의 ``Accept-Language`` 헤더를 파싱하여 지원 로케일 중 하나로 에러 메시지를 현지화하며,
    미리 정의된 status_code ↔ message_key 매핑에 없는 코드는 원본 detail을 그대로 사용합니다.

    Args:
        request (Request): FastAPI Request 객체.
                           ``Accept-Language`` 헤더 추출에 사용됩니다.
        exc (HTTPException): FastAPI 또는 Starlette가 전달하는 HTTP 예외 인스턴스.
                             ``exc.status_code``와 ``exc.detail``이 응답에 반영됩니다.

    Returns:
        JSONResponse: 다음 구조의 JSON 응답::

            {
                "status": "error",
                "message": "<현지화된 에러 메시지>",
                "status_code": <int>
            }

    Note:
        함수 내부에 정의된 ``status_to_key`` 로컬 딕셔너리를 기준으로 status_code를
        message_key로 매핑합니다. 지원 상태 코드와 키 심볼을 확인하려면
        이 함수의 코드 바디를 직접 참조하십시오.
        매핑에 없는 status_code는 ``exc.detail``을 그대로 사용합니다.
    """
    from .deps import extract_locale_from_header

    # Extract locale from request headers using centralized utility
    accept_language = request.headers.get("Accept-Language")
    locale = extract_locale_from_header(accept_language)

    # Map status codes to message keys
    status_to_key = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        413: "payload_too_large",
        422: "validation_error",
        500: "server_error",
    }

    message_key = status_to_key.get(exc.status_code)

    # If we have a predefined message key, use it; otherwise use the original detail
    if message_key:
        detail = get_message(message_key, locale, detail=exc.detail)
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
    FastAPI 전역 Pydantic 검증 오류 핸들러 (다국어 지원).

    ``app.add_exception_handler(RequestValidationError, validation_exception_handler)``로 등록합니다.
    요청 바디·쿼리·경로 파라미터의 Pydantic 유효성 검사 실패 시 호출되며,
    422 응답에 현지화된 메시지와 함께 상세 오류 목록(``errors`` 필드)을 반환합니다.

    Args:
        request (Request): FastAPI Request 객체.
                           ``Accept-Language`` 헤더 추출에 사용됩니다.
        exc (Exception): FastAPI가 전달하는 예외 객체.
                         내부적으로 ``RequestValidationError`` 타입인지 검증합니다.

    Returns:
        JSONResponse: HTTP 422 응답, 다음 구조의 JSON 포함::

            {
                "status": "error",
                "message": "<현지화된 검증 오류 메시지>",
                "status_code": 422,
                "errors": [<Pydantic 오류 상세 목록>]
            }

    Raises:
        exc: ``exc``가 ``RequestValidationError``가 아닌 경우, 원본 예외를 다시 raise합니다.
             이를 통해 의도치 않은 예외가 이 핸들러에 잘못 라우팅되는 것을 방지합니다.

    Note:
        이 핸들러는 ``RequestValidationError``를 전용으로 처리합니다.
        시그니처가 ``exc: Exception``으로 넓게 선언되어 있지만, 실제로 타입 판별(isinstance)을
        통해 ``RequestValidationError``인 경우에만 응답을 반환하며, 그 외에는 원본 예외를
        re-raise합니다. ``app.add_exception_handler(RequestValidationError, ...)``로
        등록하여 사용하십시오.

        ``errors`` 필드는 프론트엔드가 필드별 에러 메시지를 표시할 때 활용할 수 있습니다.
        단, 각 오류 항목에 사용자 입력값(``input``)이 포함될 수 있으므로
        로그 저장 시 개인정보 포함 여부를 반드시 확인하십시오.
    """
    from fastapi.exceptions import RequestValidationError

    from .deps import extract_locale_from_header

    if not isinstance(exc, RequestValidationError):
        raise exc

    # Extract locale using centralized utility
    accept_language = request.headers.get("Accept-Language")
    locale = extract_locale_from_header(accept_language)

    # Format validation errors
    errors = exc.errors()
    error_details = "; ".join([f"{err['loc'][-1]}: {err['msg']}" for err in errors])

    message = get_message("validation_error", locale, detail=error_details)

    # Use consistent response structure with http_exception_handler
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "message": message,
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "errors": errors,  # Additional field for validation details
        },
    )

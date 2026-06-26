# backend/api/deps.py

import logging
import os
from typing import Any, Callable, Dict, NamedTuple, Optional, Union

from fastapi import (
    Depends,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketException,
    status,
)
from fastapi.security import OAuth2PasswordBearer

from backend.core.config import settings

logger = logging.getLogger(__name__)

# OAuth2 스키마 정의
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# [Security] Mock User Definitions (Centralized)
# Separate mocks for different roles to detect permission issues in dev environment.
MOCK_ADMIN_USER: Dict[str, Any] = {"username": "dev_admin", "id": 1, "role": "admin"}
MOCK_REGULAR_USER: Dict[str, Any] = {"username": "dev_user", "id": 2, "role": "user"}

# Note: 'MOCK_USER' alias has been removed to enforce explicit role usage.


def _ensure_dev_environment(
    exception_factory: Callable[[], Union[HTTPException, WebSocketException]],
) -> None:
    """
    현재 실행 환경이 개발 환경(ENVIRONMENT 값이 'local' 또는 'development')인지 검증하여,
    그렇지 않은 비개발 환경인 경우 제공된 예외를 발생시킵니다.

    이 함수는 테스트용 인증 토큰이나 우회 로직이 비개발 환경(예: staging, production 등 그 외 운영 계열 환경)에서
    실수로 적용되는 것을 방지하는 보안 계층 역할을 합니다.

    Args:
        exception_factory: 발생시킬 예외를 생성하여 반환하는 콜러블 객체.
            콜러블 객체를 사용함으로써 예외 인스턴스의 불필요한 사전 생성을 방지합니다.

    Raises:
        HTTPException | WebSocketException:
            비개발 환경에서 호출될 경우, factory를 통해 생성된 예외를 즉시 발생시킵니다.
    """
    # Note: Accessing os.getenv directly as config module doesn't expose ENVIRONMENT yet.
    # TODO: Route this through backend.config.AppConfig when available.
    env = os.getenv("ENVIRONMENT", "production")
    if env not in ["local", "development"]:
        raise exception_factory()


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    HTTP 요청에 대한 현재 인증된 사용자 정보를 가져오는 FastAPI 의존성입니다.

    개발 환경에서는 테스트 및 시스템 운영을 원활하게 하기 위해
    테스트용 관리자 계정(MOCK_ADMIN_USER)을 반환합니다.
    실제 인증 로직이 추가되기 전까지 비개발 환경에서의 호출은 보안상 차단됩니다.

    Args:
        token (str): 'Authorization' 헤더를 통해 전달된 OAuth2 Bearer 토큰.
                     현재는 유효성 검증을 거치지 않으며 형태만 유지합니다.

    Returns:
        Dict[str, Any]: 사용자 정보가 담긴 딕셔너리.
            - username (str): 사용자 식별자
            - id (int): 사용자 고유 ID
            - role (str): 사용자 권한 역할 (예: 'admin', 'user')

    Raises:
        HTTPException (501 Not Implemented):
            비개발 환경(예: staging, production 등 그 외 운영 계열 환경)에서 호출될 경우 발생하는 예외.
            실제 인증 로직이 추가되기 전까지 접근을 차단하기 위함입니다.
    """
    # Default behavior: 501 Not Implemented in production
    _ensure_dev_environment(
        lambda: HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Authentication Logic is not yet implemented for production.",
        )
    )

    # TODO: Verify token logic

    return MOCK_ADMIN_USER


async def get_current_user_ws(
    websocket: WebSocket, token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    WebSocket 연결 시 쿼리 파라미터를 통해 전달된 토큰으로 인증된 사용자 정보를 반환하는 의존성입니다.

    개발 환경에서는 표준 접근 제어 테스트를 위해 테스트용 일반 계정(MOCK_REGULAR_USER)을
    반환합니다. HTTP 의존성과 마찬가지로 실제 인증 로직이 추가되기 전까지 비개발 환경에서의 호출은 차단됩니다.

    Args:
        websocket (WebSocket): 현재 연결을 시도하는 WebSocket 객체.
        token (Optional[str]): 연결 URI의 쿼리 파라미터로 전달된 인증 토큰 (예: `?token=...`).

    Returns:
        Dict[str, Any]: 사용자 정보가 담긴 딕셔너리 (username, id, role).

    Raises:
        WebSocketException (1008 Policy Violation):
            - 토큰이 쿼리 파라미터에서 누락된 경우.
            - 비개발 환경(예: staging, production 등 그 외 운영 계열 환경)에서 호출되어 인증 로직 부재로 차단될 경우.
    """
    if token is None:
        # Strictly reject missing tokens with WebSocket Close Code 1008 (Policy Violation)
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing authentication token via query parameter",
        )

    # Use WebSocketException for environment guard as well
    _ensure_dev_environment(
        lambda: WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Auth not implemented"
        )
    )

    # TODO: Verify token logic

    return MOCK_REGULAR_USER


class LanguageEntry(NamedTuple):
    """
    Accept-Language 헤더에서 파싱된 단일 언어 항목을 나타냅니다.

    Attributes:
        full_tag (str): 전체 언어 코드 (예: 'ko-KR', 'en-US').
        primary_tag (str): 기본 언어 서브태그 (예: 'ko', 'en').
        q_value (float): 우선순위를 나타내는 품질 가중치(q-value). 범위는 [0.0, 1.0].
    """

    full_tag: str
    primary_tag: str
    q_value: float


def _parse_language_entry(part: str) -> Optional[LanguageEntry]:
    """
    Accept-Language 헤더의 단일 세그먼트를 파싱하여 LanguageEntry 객체로 반환합니다.

    품질 가중치(예: 'q=0.8')를 추출하고 기본 언어 서브태그를 식별합니다.
    구체적인 언어 매칭을 보장하기 위해 와일드카드('*') 값은 무시됩니다.

    Args:
        part (str): 파싱할 Accept-Language 헤더의 단일 세그먼트 (예: 'ko-KR;q=0.9').

    Returns:
        Optional[LanguageEntry]: 파싱된 LanguageEntry 객체.
            세그먼트가 잘못된 형식이거나, 비어있거나, 와일드카드인 경우 None을 반환합니다.
    """
    part = part.strip()
    if not part:
        return None

    # Split off parameters, e.g. "en-US;q=0.8;v=1" -> ["en-US", "q=0.8", "v=1"]
    segments = [s.strip() for s in part.split(";") if s.strip()]
    if not segments:
        return None

    lang = segments[0]

    # Explicitly ignore wildcard '*' as we require concrete supported languages
    if lang == "*":
        return None

    params = segments[1:]
    q_value = 1.0

    for param in params:
        # Check for q-factor parameter
        if param.lower().startswith("q="):
            try:
                parts = param.split("=", 1)
                if len(parts) != 2:
                    return None  # Malformed q-parameter

                raw_q = parts[1].strip()
                if not raw_q:
                    return None  # Empty value

                parsed_q = float(raw_q)
                # RFC 7231: q-value must be in range [0.0, 1.0]
                if 0.0 <= parsed_q <= 1.0:
                    q_value = parsed_q
                    break  # Valid q found, stop scanning parameters
                else:
                    return None  # Out of range
            except ValueError:
                return None  # Parsing failed

    # Normalize: "en-US" -> "en"
    if not (primary_lang := lang.split("-")[0].strip()):
        return None

    return LanguageEntry(full_tag=lang, primary_tag=primary_lang, q_value=q_value)


def normalize_locale(locale: Optional[str]) -> Optional[str]:
    """
    로케일 문자열의 양쪽 공백을 제거하고 소문자로 정규화합니다.

    Args:
        locale (Optional[str]): 정규화할 원본 로케일 문자열.

    Returns:
        Optional[str]: 정규화된 소문자 로케일 문자열.
            입력값이 비어있거나 None인 경우 None을 반환합니다.
    """
    return locale.strip().lower() if locale else None


MIN_LOCALE_Q_VALUE = float("-inf")


def extract_locale_from_header(accept_language: Optional[str]) -> str:
    """
    Accept-Language 헤더에서 애플리케이션이 지원하는 가장 적합한 로케일을 추출하여 반환합니다.

    헤더 값을 파싱한 후 품질 가중치(q-value)에 따라 내림차순으로 정렬하며,
    지원되는 로케일(settings.SUPPORTED_LOCALES) 중 가장 먼저 일치하는 값을 선택합니다.
    일치하는 로케일이 없을 경우 기본 로케일(settings.DEFAULT_LOCALE)을 반환합니다.

    Args:
        accept_language (Optional[str]): 클라이언트로부터 전달받은 Accept-Language 헤더의 원본 값.

    Returns:
        str: 매칭된 지원 로케일 (예: "ko", "en") 또는 기본 로케일.
    """
    if not accept_language:
        return settings.DEFAULT_LOCALE

    # Parse all language entries and build a map: primary_tag -> highest q_value
    lang_map: Dict[str, float] = {}
    for part in accept_language.split(","):
        entry = _parse_language_entry(part)
        if not entry:
            continue

        # Keep only the highest q-value for each primary language
        if entry.q_value > lang_map.get(entry.primary_tag, MIN_LOCALE_Q_VALUE):
            lang_map[entry.primary_tag] = entry.q_value

    if not lang_map:
        logger.debug(
            "Empty lang_map for header '%s'. Falling back to default.", accept_language
        )
        return settings.DEFAULT_LOCALE

    # Sort by q-value (descending) and find first supported locale
    sorted_langs = sorted(lang_map.items(), key=lambda x: x[1], reverse=True)
    supported = set(settings.SUPPORTED_LOCALES)
    for lang, _ in sorted_langs:
        if lang in supported:
            return lang

    # Fallback to default if no supported locale found
    logger.debug(
        "No supported locale found in '%s'. Falling back to default.", accept_language
    )
    return settings.DEFAULT_LOCALE


def get_locale(
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language")
) -> str:
    """
    요청의 Accept-Language 헤더에서 적절한 로케일을 추출하여 제공하는 FastAPI 의존성입니다.

    `extract_locale_from_header` 함수를 래핑하여, 라우트 핸들러에서
    사용자의 선호 언어 설정을 문자열 형태로 자동 주입받을 수 있게 해줍니다.

    Args:
        accept_language (Optional[str]): FastAPI에 의해 주입된 Accept-Language 헤더 값.

    Returns:
        str: 결정된 최종 로케일 문자열 (예: 'ko', 'en').
    """
    return extract_locale_from_header(accept_language)

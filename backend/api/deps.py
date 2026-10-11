# backend/api/deps.py

import datetime
import logging
from datetime import timezone
from typing import Any, Callable, Dict, NamedTuple, Optional, Union

import jwt
from fastapi import (
    Depends,
    Header,
    HTTPException,
    WebSocket,
    WebSocketException,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import AppConfig, AuthConfig
from backend.core.config import settings

logger = logging.getLogger(__name__)

# HTTP Bearer 스키마 정의 (표준 JWT Bearer 인증)
http_bearer = HTTPBearer(auto_error=True)
oauth2_scheme = http_bearer  # 하위 호환성 유지용 별칭


# [Security] Mock User Definitions (Centralized)
# Separate mocks for different roles to detect permission issues in dev environment.
MOCK_ADMIN_USER: Dict[str, Any] = {"username": "dev_admin", "id": 1, "role": "admin"}
MOCK_REGULAR_USER: Dict[str, Any] = {"username": "dev_user", "id": 2, "role": "user"}

# Note: 'MOCK_USER' alias has been removed to enforce explicit role usage.


def _ensure_dev_environment(
    exception_factory: Callable[[], Union[HTTPException, WebSocketException]],
) -> None:
    """
    현재 실행 환경이 개발 환경(ENVIRONMENT 값이 'local', 'development', 'test')인지
    AppConfig를 통해 검증하여, 그렇지 않은 비개발 환경인 경우 제공된 예외를 발생시킵니다.

    Args:
        exception_factory: 발생시킬 예외를 생성하여 반환하는 콜러블 객체.

    Raises:
        HTTPException | WebSocketException:
            비개발 환경에서 호출될 경우, factory를 통해 생성된 예외를 즉시 발생시킵니다.
    """
    if not AppConfig.is_dev_environment():
        raise exception_factory()


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[datetime.timedelta] = None,
) -> str:
    """
    주어진 페이로드 데이터를 기반으로 서명된 JWT 액세스 토큰을 생성합니다.

    Args:
        data (Dict[str, Any]): 토큰에 포함할 사용자 클레임 딕셔너리.
        expires_delta (Optional[datetime.timedelta]): 만료 시간 오프셋. 미지정 시 AuthConfig 기본값 적용.

    Returns:
        str: 인코딩된 JWT 액세스 토큰 문자열.

    Raises:
        HTTPException (500): 서버에 JWT 시크릿 키가 설정되지 않은 경우.
    """
    secret_key = AuthConfig.get_jwt_secret()
    if not secret_key:
        logger.error("Authentication configuration error: JWT secret key is not set.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service configuration error",
        )

    to_encode = data.copy()
    now = datetime.datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + datetime.timedelta(
            minutes=AuthConfig.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, secret_key, algorithm=AuthConfig.get_jwt_algorithm())


def verify_token(token: str) -> Dict[str, Any]:
    """
    JWT Bearer 토큰의 유효성을 검증하고 디코딩된 사용자 정보를 반환합니다.

    Args:
        token (str): 검증할 JWT 토큰 문자열.

    Returns:
        Dict[str, Any]: 검증된 사용자 정보 딕셔너리.
            - id (Union[int, str]): 사용자 고유 ID
            - username (str): 사용자 식별자
            - role (str): 사용자 권한 역할

    Raises:
        HTTPException (401 Unauthorized):
            - 토큰이 비어있거나 형식이 올바르지 않은 경우
            - 토큰이 만료되었거나 서명이 올바르지 않은 경우
            - 필수 사용자 식별자가 누락된 경우
        HTTPException (500 Internal Server Error):
            - 서버에 JWT 시크릿 키가 설정되지 않은 경우
    """
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    cleaned_token = token.strip()
    if cleaned_token.lower().startswith("bearer "):
        cleaned_token = cleaned_token[7:].strip()

    secret_key = AuthConfig.get_jwt_secret()
    if not secret_key:
        logger.error("Authentication configuration error: JWT secret key is not set.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service configuration error",
        )

    try:
        payload = jwt.decode(
            cleaned_token,
            secret_key,
            algorithms=[AuthConfig.get_jwt_algorithm()],
            options={"require": ["exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        logger.warning("Token verification failed: Signature has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        logger.warning(
            "Token verification failed: Invalid token (%s)", type(exc).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    raw_id = payload.get("id") or payload.get("sub")
    raw_username = payload.get("username") or payload.get("sub")
    role = payload.get("role", "user")

    if raw_id is None and raw_username is None:
        logger.warning(
            "Token verification failed: Missing subject/id claims in payload"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: missing user identification",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: Union[int, str]
    if isinstance(raw_id, str) and raw_id.isdigit():
        user_id = int(raw_id)
    elif raw_id is not None:
        user_id = raw_id
    else:
        user_id = str(raw_username)

    username = str(raw_username if raw_username is not None else user_id)

    return {
        "id": user_id,
        "username": username,
        "role": str(role),
    }


def get_current_user(
    credentials: Union[HTTPAuthorizationCredentials, str] = Depends(http_bearer),
) -> Dict[str, Any]:
    """
    HTTP 요청의 Authorization Bearer 토큰을 검증하여 현재 인증된 사용자 정보를 반환하는 FastAPI 의존성입니다.

    Args:
        credentials (Union[HTTPAuthorizationCredentials, str]):
            'Authorization: Bearer <token>' 헤더를 통해 전달된 자격 증명 또는 직접 전달된 토큰 문자열.

    Returns:
        Dict[str, Any]: 사용자 정보가 담긴 딕셔너리 (id, username, role).

    Raises:
        HTTPException (401 Unauthorized): 토큰이 만료되었거나 서명이 유효하지 않은 경우.
        HTTPException (500 Internal Server Error): 서버 JWT 시크릿 키 미설정.
    """
    token_str = (
        credentials.credentials
        if isinstance(credentials, HTTPAuthorizationCredentials)
        else credentials
    )
    return verify_token(token_str)


async def get_current_user_ws(
    websocket: WebSocket,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    sec_websocket_protocol: Optional[str] = Header(
        None, alias="Sec-WebSocket-Protocol"
    ),
) -> Dict[str, Any]:
    """
    WebSocket 연결 시 HTTP 헤더(Authorization 또는 Sec-WebSocket-Protocol)를 통해 전달된
    토큰으로 인증된 사용자 정보를 반환하는 의존성입니다.

    보안/개인정보보호 정책:
    - 액세스 로그에 베어러 토큰이 영구 노출되는 것을 방지하기 위해 URL 쿼리 파라미터를 통한
      토큰 전송은 원천 금지되며, 시도 시 즉시 1008 Policy Violation으로 연결을 거부합니다.

    Args:
        websocket (WebSocket): 현재 연결을 시도하는 WebSocket 객체.
        authorization (Optional[str]): Authorization 헤더 (예: 'Bearer <token>').
        sec_websocket_protocol (Optional[str]): Sec-WebSocket-Protocol 헤더.

    Returns:
        Dict[str, Any]: 사용자 정보가 담긴 딕셔너리 (id, username, role).

    Raises:
        WebSocketException (1008 Policy Violation):
            - 쿼리 파라미터로 토큰을 전송하려 한 경우.
            - 인증 헤더가 누락되었거나 비어있는 경우.
            - 토큰이 유효하지 않거나, 만료되었거나, 검증에 실패한 경우.
    """
    # 1. 쿼리 스트링 토큰 전송 차단 (URL 로깅에 의한 토큰 노출 방지)
    query_params = getattr(websocket, "query_params", {})
    if "token" in query_params or query_params.get("token"):
        logger.warning(
            "WebSocket rejected: Query parameter authentication is forbidden (URL logging exposure prevention)."
        )
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Query parameter token transmission is forbidden. Use Authorization or Sec-WebSocket-Protocol header.",
        )

    # 2. 헤더에서 토큰 추출 (Authorization 우선, Sec-WebSocket-Protocol 차선)
    token: Optional[str] = authorization
    if not token and hasattr(websocket, "headers"):
        token = websocket.headers.get("authorization")

    if not token:
        protocol_header = sec_websocket_protocol
        if not protocol_header and hasattr(websocket, "headers"):
            protocol_header = websocket.headers.get("sec-websocket-protocol")

        if protocol_header:
            # "Bearer, <token>" 또는 "access_token, <token>" 또는 단독 "<token>" 파싱
            protocols = [p.strip() for p in protocol_header.split(",") if p.strip()]
            for p in protocols:
                if p.lower() not in ("bearer", "access_token", "jwt", "flownote_sync"):
                    token = p
                    break

    if not token or not token.strip():
        logger.warning(
            "WebSocket rejected: Missing authentication header (Authorization / Sec-WebSocket-Protocol)"
        )
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing authentication header",
        )

    try:
        return verify_token(token)
    except HTTPException as exc:
        logger.warning(
            "WebSocket authentication failed (code=%s)",
            status.WS_1008_POLICY_VIOLATION,
        )
        detail_msg = (
            exc.detail if isinstance(exc.detail, str) else "Authentication failed"
        )
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=detail_msg,
        ) from exc


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

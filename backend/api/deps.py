# backend/api/deps.py

import os
from typing import Optional, Dict, Any, Callable, Union, NamedTuple
from fastapi import (
    Depends,
    HTTPException,
    status,
    WebSocket,
    Query,
    WebSocketException,
    Header,
)
from fastapi.security import OAuth2PasswordBearer
from backend.core.config import settings

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
    [Security Guard]
    Block mock-based auth outside local/development environments.

    Args:
        exception_factory: A callable that returns the exception to raise.
                           Using a factory ensures the exception is created
                           (and stack trace captured) only when actually raised.
    """
    # Note: Accessing os.getenv directly as config module doesn't expose ENVIRONMENT yet.
    # TODO: Route this through backend.config.AppConfig when available.
    env = os.getenv("ENVIRONMENT", "production")
    if env not in ["local", "development"]:
        raise exception_factory()


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    HTTP requesting user dependency.
    Returns Admin user in dev environment to facilitate system operations.
    """
    # Default behavior: 501 Not Implemented in production
    _ensure_dev_environment(
        lambda: HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Authentication Logic is not yet implemented for production.",
        )
    )

    # TODO: [Phase 2] verify_token(token)

    return MOCK_ADMIN_USER


async def get_current_user_ws(
    websocket: WebSocket, token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    WebSocket connecting user dependency.
    Returns Regular user in dev environment to test standard access controls.
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

    # TODO: [Phase 2] Verify token logic

    return MOCK_REGULAR_USER


class LanguageEntry(NamedTuple):
    full_tag: str
    primary_tag: str
    q_value: float


def _parse_language_entry(part: str) -> Optional[LanguageEntry]:
    """
    Helper to parse a single Accept-Language entry.
    Returns LanguageEntry(full_tag, primary_tag, q_value) or None if invalid.
    Wildcard '*' is explicitly ignored to enforce concrete language matching.
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
    primary_lang = lang.split("-")[0].strip()
    if not primary_lang:
        return None

    return LanguageEntry(full_tag=lang, primary_tag=primary_lang, q_value=q_value)


def extract_locale_from_header(accept_language: Optional[str]) -> str:
    """
    Extract locale from Accept-Language header string.
    This is a public utility that can be used outside of FastAPI dependency injection.

    Args:
        accept_language: Accept-Language header value

    Returns:
        Locale string (e.g., "ko", "en") or DEFAULT_LOCALE if none found
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
        if (
            entry.primary_tag not in lang_map
            or entry.q_value > lang_map[entry.primary_tag]
        ):
            lang_map[entry.primary_tag] = entry.q_value

    # Sort by q-value (descending) and find first supported locale
    sorted_langs = sorted(lang_map.items(), key=lambda x: x[1], reverse=True)
    for lang, _ in sorted_langs:
        if lang in settings.SUPPORTED_LOCALES:
            return lang

    # Fallback to default if no supported locale found
    return settings.DEFAULT_LOCALE


def get_locale(
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language")
) -> str:
    """
    FastAPI dependency to extract locale from Accept-Language header.
    Uses extract_locale_from_header internally.
    """
    return extract_locale_from_header(accept_language)

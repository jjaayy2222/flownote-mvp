# backend/api/deps.py

import os
from typing import Optional, Dict, Any, Callable, Union
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
from backend.services.i18n_service import SUPPORTED_LOCALES, DEFAULT_LOCALE

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


def get_locale(
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language")
) -> str:
    """
    Parses Accept-Language header to determine preferred locale.
    Handles q-factors (quality values), additional parameters, and fallback.
    """
    if not accept_language:
        return DEFAULT_LOCALE

    # Map primary language to its highest q-value found for deduplication
    lang_map = {}

    for part in accept_language.split(","):
        part = part.strip()
        if not part:
            continue

        # Split off parameters, e.g. "en-US;q=0.8;v=1" -> ["en-US", "q=0.8", "v=1"]
        segments = [segment.strip() for segment in part.split(";") if segment.strip()]
        if not segments:
            continue

        lang = segments[0]
        params = segments[1:]

        # Default q-value is 1.0 if not specified
        q_value = 1.0

        for param in params:
            # Check for q-factor parameter
            if param.lower().startswith("q="):
                try:
                    parts = param.split("=", 1)
                    if len(parts) == 2:
                        raw_q = parts[1].strip()
                        if raw_q:
                            parsed_q = float(raw_q)
                            # RFC 7231: q-value must be in range [0.0, 1.0]
                            if 0.0 <= parsed_q <= 1.0:
                                q_value = parsed_q
                            else:
                                q_value = 0.0  # Out of range -> lowest priority
                        else:
                            q_value = 0.0  # Empty value
                    else:
                        q_value = 0.0  # Malformed
                except ValueError:
                    q_value = 0.0  # Parsing failed

                # Once we found the q parameter (valid or not), we stop looking for it in this part
                break

        # Normalize: "en-US" -> "en"
        # Note: We prioritize the primary tag because our SUPPORTED_LOCALES rely on generic codes ('en', 'ko').
        primary_lang = lang.split("-")[0].strip()

        if primary_lang:
            # Keep the highest q-value for this language
            current_max = lang_map.get(primary_lang, 0.0)
            lang_map[primary_lang] = max(current_max, q_value)

    # Convert to list and sort by q-value descending
    languages = list(lang_map.items())
    languages.sort(key=lambda x: x[1], reverse=True)

    # Find first supported locale
    for lang, _ in languages:
        if lang in SUPPORTED_LOCALES:
            return lang

    return DEFAULT_LOCALE

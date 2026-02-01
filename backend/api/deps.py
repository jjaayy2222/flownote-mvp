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
    Parses the Accept-Language header to determine the preferred locale.
    Handles q-factors (quality values) and fallback to default locale.
    Example header: "fr-CH, fr;q=0.9, en;q=0.8, de;q=0.7, *;q=0.5"
    """
    if not accept_language:
        return DEFAULT_LOCALE

    # Parse languages and q-values
    languages = []
    for part in accept_language.split(","):
        part = part.strip()
        if not part:
            continue

        if ";q=" in part:
            part_split = part.split(";q=")
            lang = part_split[0]
            try:
                q_value = float(part_split[1])
            except ValueError:
                q_value = 1.0  # Default fallback if parsing fails
        else:
            lang = part
            q_value = 1.0

        # Normalize: "en-US" -> "en"
        primary_lang = lang.split("-")[0].strip()
        languages.append((primary_lang, q_value))

    # Sort by q-value descending
    languages.sort(key=lambda x: x[1], reverse=True)

    # Find first supported locale
    for lang, _ in languages:
        if lang in SUPPORTED_LOCALES:
            return lang

    return DEFAULT_LOCALE

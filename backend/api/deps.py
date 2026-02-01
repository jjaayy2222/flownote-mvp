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
    accept_language: str = Header(default=DEFAULT_LOCALE, alias="Accept-Language")
) -> str:
    """
    Parses the Accept-Language header to determine the preferred locale.
    Returns the first matching supported locale or the default locale.
    """
    if not accept_language:
        return DEFAULT_LOCALE

    # e.g. "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    # Simple parsing: check the first preferred language
    preferred = accept_language.split(",")[0].strip()
    # Handle "ko-KR" -> "ko"
    primary_tag = preferred.split("-")[0]

    if primary_tag in SUPPORTED_LOCALES:
        return primary_tag

    return DEFAULT_LOCALE

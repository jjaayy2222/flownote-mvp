# backend/api/deps.py

import os
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, WebSocket, Query, WebSocketException
from fastapi.security import OAuth2PasswordBearer

# OAuth2 스키마 정의
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# [Security] Mock User Definitions (Centralized)
# Separate mocks for different roles to detect permission issues in dev environment.
MOCK_ADMIN_USER: Dict[str, Any] = {"username": "dev_admin", "id": 1, "role": "admin"}
MOCK_REGULAR_USER: Dict[str, Any] = {"username": "dev_user", "id": 2, "role": "user"}

# Note: 'MOCK_USER' alias has been removed to enforce explicit role usage.


def _ensure_dev_environment(exception_to_raise: Exception) -> None:
    """
    [Security Guard]
    Block mock-based auth outside local/development environments.
    Accepts a specific exception instance to raise, allowing caller to control
    whether to fail with HTTPException (for REST) or WebSocketException (for WS).
    """
    # Note: Accessing os.getenv directly as config module doesn't expose ENVIRONMENT yet.
    # TODO: Route this through backend.config.AppConfig when available.
    env = os.getenv("ENVIRONMENT", "production")
    if env not in ["local", "development"]:
        raise exception_to_raise


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    HTTP requesting user dependency.
    Returns Admin user in dev environment to facilitate system operations.
    """
    # Default behavior: 501 Not Implemented in production
    _ensure_dev_environment(
        HTTPException(
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
        WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Auth not implemented"
        )
    )

    # TODO: [Phase 2] Verify token logic

    return MOCK_REGULAR_USER

# backend/api/deps.py

import os
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, WebSocket, Query
from fastapi.security import OAuth2PasswordBearer

# OAuth2 스키마 정의
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# [Security] Mock User Definitions (Centralized)
# Separate mocks for different roles to detect permission issues in dev environment.
MOCK_ADMIN_USER: Dict[str, Any] = {"username": "dev_admin", "id": 1, "role": "admin"}
MOCK_REGULAR_USER: Dict[str, Any] = {"username": "dev_user", "id": 2, "role": "user"}

# Backwards compatibility alias
MOCK_USER = MOCK_ADMIN_USER


def _ensure_dev_environment(
    status_code: int = status.HTTP_501_NOT_IMPLEMENTED,
    detail: str = "Authentication Logic is not yet implemented for production.",
) -> None:
    """
    [Security Guard]
    Block mock-based auth outside local/development environments.
    """
    # Note: Accessing os.getenv directly as config module doesn't expose ENVIRONMENT yet.
    env = os.getenv("ENVIRONMENT", "production")
    if env not in ["local", "development"]:
        raise HTTPException(status_code=status_code, detail=detail)


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    HTTP requesting user dependency.
    Returns Admin user in dev environment to facilitate system operations.
    """
    # Default behavior: 501 Not Implemented in production
    _ensure_dev_environment()

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
        # Strictly reject missing tokens
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token via query parameter",
        )

    # WebSocket handshake failure should be 403 or similar, not 501
    _ensure_dev_environment(
        status_code=status.HTTP_403_FORBIDDEN, detail="Auth not implemented"
    )

    # TODO: [Phase 2] Verify token logic

    return MOCK_REGULAR_USER

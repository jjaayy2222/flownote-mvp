# backend/api/deps.py

import os
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, WebSocket, Query
from fastapi.security import OAuth2PasswordBearer

# OAuth2 스키마 정의
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# [Security] Mock User Definition (Centralized)
MOCK_USER = {"username": "dev_user", "id": 1, "role": "admin"}


def _ensure_dev_environment():
    """
    [Security Guard]
    프로덕션 환경에서 실수로 인증이 우회되는 것을 방지합니다.
    환경 변수 `ENVIRONMENT`가 'local' 또는 'development'일 때만 통과합니다.
    """
    env = os.getenv("ENVIRONMENT", "production")
    if env not in ["local", "development"]:
        # 실제 구현이 없는 상태에서 프로덕션 호출 시 명확하게 실패
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Authentication Logic is not yet implemented for production.",
        )


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    HTTP 요청에 대한 JWT 인증 의존성 함수입니다.
    """
    # 1. Security Check
    _ensure_dev_environment()

    # TODO: [Phase 2] Implement Logic
    # verify_token(token)

    return MOCK_USER


async def get_current_user_ws(
    websocket: WebSocket, token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    WebSocket 연결을 위한 인증 의존성 함수입니다.
    쿼리 파라미터 `token`을 검증합니다.
    """
    # 1. Missing Token Handling
    if token is None:
        # 토큰이 없으면 핸드쉐이크 단계에서 즉시 거부 (401 Unauthorized)
        # 의도치 않은 익명 접근(Anonymous)을 방지합니다.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token via query parameter",
        )

    # 2. Security Check (Environment)
    try:
        _ensure_dev_environment()
    except HTTPException:
        # WebSocket 연결 시점의 서버 에러/구현 미비는 1011(Internal Error) 또는 403으로 처리
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Auth not implemented"
        )

    # TODO: [Phase 2] Verify token logic

    return MOCK_USER

# backend/api/deps.py

from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, WebSocket, Query
from fastapi.security import OAuth2PasswordBearer

# OAuth2 스키마 정의 (스캐폴딩)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    HTTP 요청에 대한 JWT 인증 의존성 함수입니다.
    현재는 스캐폴딩 단계로, 실제 검증 로직은 추후 구현됩니다.
    """
    # TODO: [Phase 2] Implement JWT decoding
    # TODO: [Phase 2] Validate token and fetch user from DB

    # Mock return for development
    return {"username": "dev_user", "id": 1, "role": "admin"}


async def get_current_user_ws(
    websocket: WebSocket, token: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    WebSocket 연결을 위한 인증 의존성 함수입니다.
    쿼리 파라미터 `token`을 통해 인증을 수행합니다.
    """
    if token is None:
        # TODO: [Phase 2] Decide whether to reject connection or allow anonymous with restrictions
        # await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        pass

    # TODO: [Phase 2] Verify token logic similar to get_current_user

    return {"username": "ws_user", "id": 1, "role": "user"}

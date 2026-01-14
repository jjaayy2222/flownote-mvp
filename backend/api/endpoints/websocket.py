# backend/api/endpoints/websocket.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from backend.api import deps
import logging

# 로거 설정
logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, current_user: dict = Depends(deps.get_current_user_ws)
):
    """
    WebSocket 연결 엔드포인트

    쿼리 파라미터 `token`을 통해 JWT 인증을 수행하며,
    인증된 사용자만 연결이 허용됩니다.

    Note: 현재는 Phase 1 구현 준비 단계로 기본 Echo 로직만 포함되어 있습니다.
    추후 ConnectionManager 및 Redis Pub/Sub 연동이 필요합니다.
    """
    # 인증 성공 시 연결 수락
    await websocket.accept()
    logger.info(
        f"WebSocket Client Connected: UserID={current_user.get('id')}, Username={current_user.get('username')}"
    )

    try:
        while True:
            data = await websocket.receive_text()
            # TODO: Handle messages (e.g., subscription requests)
            await websocket.send_text(f"Message received: {data}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket Client Disconnected: UserID={current_user.get('id')}")

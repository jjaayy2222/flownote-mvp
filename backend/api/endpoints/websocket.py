# backend/api/endpoints/websocket.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from backend.api import deps
from backend.services.websocket_manager import manager
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
    """
    # ConnectionManager를 통해 연결 수락 및 관리
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            # 받은 메시지를 로깅하고 (필요 시 브로드캐스트)
            logger.debug(
                f"Received message from {current_user.get('username')}: {data}"
            )

            # 현재는 단순 Echo 대신 브로드캐스트 예시 주석 처리
            # await manager.broadcast(f"Broadcasting: {data}")
            await websocket.send_text(f"Echo: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket Client Disconnected: UserID={current_user.get('id')}")

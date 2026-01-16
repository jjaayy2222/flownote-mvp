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

    - 쿼리 파라미터 `token`을 통해 JWT 인증 수행 (deps.get_current_user_ws)
    - ConnectionManager를 통한 연결 수명 주기 관리 (자동 정리 보장)
    """
    # [Connection Phase]
    # 인증된 사용자 정보와 함께 연결 수락
    await manager.connect(websocket, current_user)

    try:
        # [Communication Phase]
        while True:
            data = await websocket.receive_text()
            # 로깅: 실제 운영 환경에서는 debug 레벨 권장
            logger.debug(
                f"Received message from {current_user.get('username')}: {data}"
            )

            # Simple Echo (Phase 1)
            # 향후 manager.broadcast() 또는 개별 응답 로직으로 대체
            await websocket.send_text(f"Echo: {data}")

    except WebSocketDisconnect:
        logger.info(
            f"WebSocket Client Disconnected (Graceful): UserID={current_user.get('id')}"
        )

    except Exception as e:
        logger.error(f"WebSocket Error (Unexpected): {e}", exc_info=True)

    finally:
        # [Cleanup Phase]
        # 어떤 이유로든 루프가 종료되면 반드시 연결 목록에서 제거
        manager.disconnect(websocket)

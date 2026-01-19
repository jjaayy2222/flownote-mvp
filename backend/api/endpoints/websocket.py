# backend/api/endpoints/websocket.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from backend.api import deps
from backend.services.websocket_manager import manager
from backend.services.redis_pubsub import redis_broadcaster
import logging

# 로거 설정
logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health/metrics", tags=["System"])
async def get_ws_health():
    """WebSocket 시스템 지표 및 상태 조회 엔드포인트"""
    metrics = manager.get_metrics()
    return {
        "status": "healthy",
        "connections": {
            "active": metrics["active_connections"],
            "peak": metrics["peak_connections"],
        },
        "performance": {
            "window_seconds": WebSocketConfig.METRICS_WINDOW_SECONDS,
            "broadcast_tps": metrics["broadcast_tps"],
            "message_tps": metrics["message_tps"],
            "total_broadcasts": metrics["total_broadcasts"],
            "total_messages": metrics["total_messages"],
            "total_data_bytes": metrics["total_bytes"],
            "total_data_mb": round(metrics["total_bytes"] / (1024 * 1024), 2),
        },
        "redis": {
            "connected": redis_broadcaster.is_connected(),
            "channel": manager.channel_name,
        },
        "uptime_seconds": metrics["uptime_seconds"],
    }


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, current_user: dict = Depends(deps.get_current_user_ws)
):
    """
    WebSocket 연결 엔드포인트

    - 쿼리 파라미터 `token`을 통해 JWT 인증 수행 (deps.get_current_user_ws)
    - ConnectionManager를 통한 연결 수명 주기 및 컨텍스트 관리
    """
    # [Connection Phase]
    # 인증된 사용자 정보와 함께 연결 수락
    await manager.connect(websocket, current_user)

    close_code = 1000
    close_reason = None

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

    except WebSocketDisconnect as e:
        # 클라이언트가 연결을 끊은 경우
        close_code = e.code
        close_reason = e.reason
        logger.info(
            f"WebSocket Client Disconnected: UserID={current_user.get('id')}, Code={close_code}"
        )

    except Exception as e:
        logger.error(f"WebSocket Error (Unexpected): {e}", exc_info=True)
        close_code = 1011  # Internal Error

    finally:
        # [Cleanup Phase]
        # 루프 종료 시 (에러, 연결 끊김 등) 반드시 연결 목록에서 제거 및 소켓 종료
        await manager.disconnect(websocket, code=close_code, reason=close_reason)

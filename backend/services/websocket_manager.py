# backend/services/websocket_manager.py

from typing import List, Dict, Any
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket 연결 관리자
    - 활성 연결 목록 관리 및 연결 수명 주기 제어
    - 사용자 정보 로깅을 통한 관찰 가능성(Observability) 제공
    - 데드 커넥션(Dead Connection) 자동 정리
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, user_info: Dict[str, Any]):
        """클라이언트 연결 수락 및 목록에 추가 (사용자 정보 로깅 포함)"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket Client Connected: UserID={user_info.get('id')}, "
            f"Username={user_info.get('username')}. "
            f"Active connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """클라이언트 연결 해제 및 목록에서 제거"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"WebSocket Client Removed. Active connections: {len(self.active_connections)}"
            )

    async def broadcast(self, message: str):
        """
        모든 활성 연결에 메시지 전송
        전송 실패 시 해당 연결을 Dead Connection으로 간주하고 목록에서 제거하여 리소스 누수 방지
        """
        failed_connections: List[WebSocket] = []

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to broadcast message to client: {e}")
                failed_connections.append(connection)

        # Clean up dead connections
        if failed_connections:
            logger.info(
                f"Pruning {len(failed_connections)} dead connections found during broadcast."
            )
            for dead_ws in failed_connections:
                self.disconnect(dead_ws)


# 싱글톤 인스턴스 생성
manager = ConnectionManager()

# backend/services/websocket_manager.py

from typing import List
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket 연결 관리자
    - 활성 연결 목록 관리
    - 연결 수락 및 해제
    - 메시지 브로드캐스트
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """클라이언트 연결 수락 및 목록에 추가"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket Client connected. Active connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """클라이언트 연결 해제 및 목록에서 제거"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"WebSocket Client disconnected. Active connections: {len(self.active_connections)}"
            )

    async def broadcast(self, message: str):
        """모든 활성 연결에 메시지 전송"""
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send message to client: {e}")
                # 전송 실패한 연결은 정리 대상으로 고려할 수 있음


# 싱글톤 인스턴스 생성
manager = ConnectionManager()

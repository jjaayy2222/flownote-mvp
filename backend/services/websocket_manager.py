import asyncio
from typing import List, Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    """Type-safe user context for WebSocket connections"""

    user_id: int
    username: str
    role: str


class ConnectionManager:
    """
    WebSocket 연결 관리자
    - 활성 연결 목록 관리 및 연결 수명 주기 제어
    - 사용자 정보 매핑을 통한 관찰 가능성(Observability) 제공
    - Concurrency-safe Broadcasting & Dead Connection Pruning
    """

    def __init__(self):
        # WebSocket 객체를 Key로, 사용자 정보를 Value로 저장하여 O(1) 접근 및 매핑 유지
        self.active_connections: Dict[WebSocket, UserContext] = {}

    async def connect(self, websocket: WebSocket, user_info: Dict[str, Any]):
        """클라이언트 연결 수락 및 컨텍스트 저장"""
        await websocket.accept()

        # Convert dict to typed context
        context = UserContext(
            user_id=user_info.get("id", 0),
            username=user_info.get("username", "unknown"),
            role=user_info.get("role", "user"),
        )

        self.active_connections[websocket] = context
        logger.info(
            f"WebSocket Client Connected: {context}. "
            f"Active connections: {len(self.active_connections)}"
        )

    async def disconnect(self, websocket: WebSocket):
        """클라이언트 연결 해제, 목록 제거 및 명시적 소켓 종료"""
        context = self.active_connections.pop(websocket, None)

        if context:
            logger.info(
                f"WebSocket Client Removed: {context}. "
                f"Active connections: {len(self.active_connections)}"
            )

        # Ensure socket is closed explicitly to prevent zombies
        try:
            # 1000 Normal Closure
            await websocket.close(code=1000)
        except Exception as exc:
            # Log unexpected shutdown issues without failing the cleanup path
            logger.debug(
                "Best-effort WebSocket close failed (possibly already closed or connection lost).",
                exc_info=exc,
            )

    async def _prune_connection(self, websocket: WebSocket) -> None:
        """
        [Helper] Dead Connection 안전 제거
        예외를 내부에서 처리하여 상위 호출자(Broadcast 등)의 흐름을 방해하지 않음
        """
        try:
            await self.disconnect(websocket)
        except Exception as exc:
            logger.warning("Error while pruning dead connection: %s", exc)

    async def broadcast(self, message: str):
        """
        모든 활성 연결에 메시지 전송 (Concurrency Safe)
        """
        failed_connections: List[WebSocket] = []

        # [Critical Fix] Take a snapshot of keys to avoid RuntimeError during concurrent modification
        active_sockets = list(self.active_connections.keys())

        for connection in active_sockets:
            try:
                await connection.send_text(message)
            except Exception as e:
                # Enhance error log with user context
                context = self.active_connections.get(connection)
                user_id = f"User({context.user_id})" if context else "Unknown"
                logger.error(f"Failed to broadcast to {user_id}: {e}")

                failed_connections.append(connection)

        # Prune dead connections found during broadcast
        if failed_connections:
            logger.info(
                f"Pruning {len(failed_connections)} dead connections found during broadcast."
            )

            # Run disconnects concurrently to avoid serial latency issues
            # Using _prune_connection ensures exceptions are handled individually
            await asyncio.gather(
                *(self._prune_connection(dead_ws) for dead_ws in failed_connections)
            )


# 싱글톤 인스턴스 생성
manager = ConnectionManager()

# backend/services/websocket_manager.py

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from fastapi import WebSocket, WebSocketDisconnect
from backend.services.redis_pubsub import redis_client

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
    - Redis Pub/Sub 통합으로 멀티 프로세스 브로드캐스트 지원
    - 활성 연결 목록 관리 및 연결 수명 주기 제어
    - Concurrency-safe Broadcasting & Dead Connection Pruning
    """

    def __init__(self):
        self.active_connections: Dict[WebSocket, UserContext] = {}
        self.channel_name = "flownote_sync"
        self.redis_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """
        시스템 시작 시 호출: Redis 연결 및 구독 리스너 실행
        실패 시 로컬 전용 모드로 동작 (Graceful Degradation)
        """
        try:
            await redis_client.connect()
            # 구독 리스너를 비동기 태스크로 실행
            self.redis_task = asyncio.create_task(
                redis_client.subscribe(self.channel_name, self._local_broadcast)
            )
            logger.info(
                f"ConnectionManager initialized. Listening on Redis channel: {self.channel_name}"
            )
        except Exception as e:
            logger.warning(
                f"Redis initialization failed ({e}). ConnectionManager running in LOCAL broadcast mode."
            )

    async def shutdown(self):
        """시스템 종료 시 호출: 리소스 정리"""
        if self.redis_task:
            self.redis_task.cancel()
            try:
                await self.redis_task
            except asyncio.CancelledError:
                pass

        await redis_client.disconnect()

        # 모든 활성 연결 종료 (Graceful Close)
        active_sockets = list(self.active_connections.keys())
        for ws in active_sockets:
            await self.disconnect(ws)

    async def connect(self, websocket: WebSocket, user_info: Dict[str, Any]):
        """클라이언트 연결 수락 및 컨텍스트 저장"""
        await websocket.accept()

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

        try:
            await websocket.close(code=1000)
        except Exception as exc:
            logger.debug(
                "Best-effort WebSocket close failed (possibly already closed or connection lost).",
                exc_info=exc,
            )

    async def _prune_connection(self, websocket: WebSocket) -> None:
        """[Helper] Dead Connection 안전 제거"""
        try:
            await self.disconnect(websocket)
        except (WebSocketDisconnect, RuntimeError) as exc:
            logger.warning(f"Connection pruning failed (expected network issue): {exc}")
        except Exception:
            logger.error(
                "Error while pruning dead connection (unexpected bug)", exc_info=True
            )

    async def broadcast(self, message: str):
        """
        메시지 전파 진입점:
        - Redis 가용 시: Redis Publish -> (Listener) -> _local_broadcast
        - Redis 불가 시: 직접 _local_broadcast (Fallback)
        """
        if redis_client.redis:
            try:
                await redis_client.publish(self.channel_name, message)
            except Exception as e:
                logger.error(
                    f"Redis publish failed: {e}. Falling back to local broadcast."
                )
                await self._local_broadcast(message)
        else:
            await self._local_broadcast(message)

    async def _local_broadcast(self, message: str):
        """
        [Internal] 실제 로컬 연결된 클라이언트들에게 메시지 전송
        (Redis Listener 또는 Local Fallback에 의해 호출됨)
        """
        failed_connections: List[WebSocket] = []
        active_sockets = list(self.active_connections.keys())

        for connection in active_sockets:
            try:
                await connection.send_text(message)
            except Exception as e:
                context = self.active_connections.get(connection)
                user_id = f"User({context.user_id})" if context else "Unknown"
                logger.error(f"Failed to broadcast to {user_id}: {e}")
                failed_connections.append(connection)

        if failed_connections:
            logger.info(
                f"Pruning {len(failed_connections)} dead connections found during broadcast."
            )
            results = await asyncio.gather(
                *(self._prune_connection(dead_ws) for dead_ws in failed_connections),
                return_exceptions=True,
            )

            systemic_errors = [r for r in results if isinstance(r, BaseException)]
            if systemic_errors:
                logger.error(
                    f"Systemic failures during connection pruning: {len(systemic_errors)} errors detected."
                )


# 싱글톤 인스턴스 생성
manager = ConnectionManager()

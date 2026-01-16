# backend/services/websocket_manager.py

import asyncio
import logging
from collections import Counter
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from fastapi import WebSocket, WebSocketDisconnect
from backend.services.redis_pubsub import redis_broadcaster

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
    - WebSocket 라이프사이클 관리 (Connect/Disconnect)
    - RedisBroadcaster를 통한 메시지 전파 (Orchestration delegated)
    - 단순화된 에러 핸들링 및 병렬 정리 구현
    """

    def __init__(self):
        self.active_connections: Dict[WebSocket, UserContext] = {}
        # Channel name is kept simple here; could be moved to config if needed
        self.channel_name = "flownote_sync"

    async def initialize(self):
        """시스템 시작 시 호출: Redis 오케스트레이션 시작"""
        await redis_broadcaster.start(self.channel_name, self._local_broadcast)

    async def shutdown(self):
        """시스템 종료 시 호출: Redis 정리 및 모든 소켓 병렬 종료"""
        await redis_broadcaster.stop()

        # Parallel shutdown for performance: avoid serial teardown latency
        active_sockets = list(self.active_connections.keys())
        if active_sockets:
            # Run disconnects concurrently
            await asyncio.gather(
                *(self.disconnect(ws) for ws in active_sockets), return_exceptions=True
            )

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
            # Minimal log mostly for debug since connection might be already closed
            logger.debug("WebSocket close skipped/failed", exc_info=exc)

    async def _prune_connection(self, websocket: WebSocket) -> None:
        """[Helper] Dead Connection 정리 (간소화됨)"""
        try:
            await self.disconnect(websocket)
        except WebSocketDisconnect:
            # Expected network-level issue; keep log minimal
            logger.debug("WebSocket already disconnected during pruning.")
        except Exception:
            # Unexpected programmer errors: Log full traceback
            logger.error(
                "Error while pruning dead connection (unexpected bug)", exc_info=True
            )

    async def broadcast(self, message: str):
        """메시지 전파 (Redis 우선, 실패 시 로컬 Fallback 자동 처리)"""
        await redis_broadcaster.publish_or_fallback(
            self.channel_name, message, self._local_broadcast
        )

    async def _local_broadcast(self, message: str):
        """[Internal] 실제 로컬 연결된 클라이언트들에게 메시지 전송 및 정리"""
        failed_connections: List[WebSocket] = []
        active_sockets = list(self.active_connections.keys())

        for connection in active_sockets:
            try:
                await connection.send_text(message)
            except Exception as e:
                # Log context for better observability
                context = self.active_connections.get(connection)
                user_str = f"User({context.user_id})" if context else "Unknown"
                logger.error(f"Failed to broadcast to {user_str}: {e}")
                failed_connections.append(connection)

        if failed_connections:
            logger.info(
                "Pruning %d dead connections found during broadcast.",
                len(failed_connections),
            )
            # Parallel pruning using asyncio.gather for performance
            results = await asyncio.gather(
                *(self._prune_connection(dead_ws) for dead_ws in failed_connections),
                return_exceptions=True,
            )

            # [Added] Monitor pruning errors with aggregation for actionable insights
            errors = [r for r in results if isinstance(r, Exception)]
            if errors:
                error_counts = Counter(type(e).__name__ for e in errors)
                logger.warning(
                    f"Errors during connection pruning: {len(errors)} total. "
                    f"Breakdown: {dict(error_counts)}. "
                    f"First Error Detail: {repr(errors[0])}"
                )


# 싱글톤 인스턴스 생성
manager = ConnectionManager()

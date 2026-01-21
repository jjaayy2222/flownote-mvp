# backend/services/websocket_manager.py

import asyncio
import logging
import time
from collections import Counter, deque
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from fastapi import WebSocket
from starlette.websockets import WebSocketState, WebSocketDisconnect
from backend.services.redis_pubsub import redis_broadcaster
from backend.services.compression_service import compress_payload
from backend.config import WebSocketConfig

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

        # [Metrics] 실시간 관측성 강화를 위한 지표 변수
        self._start_time = time.time()
        self._total_messages_sent = 0
        self._total_broadcasts_sent = 0  # [Metrics] 브로드캐스트 이벤트 단위 지표
        self._total_bytes_sent = 0
        self._peak_connections = 0

        # [Metrics] TPS 산출을 위한 샘플링 (설정 기반 상한 설정)
        # 1. 브로드캐스트 이벤트 단위 (Broadcast TPS)
        self._broadcast_timestamps = deque(
            maxlen=WebSocketConfig.METRICS_MAX_TPS
            * WebSocketConfig.METRICS_WINDOW_SECONDS
        )
        # 2. 개별 수신자 발송 단위 (Message/Recipient TPS)
        self._message_timestamps = deque(
            maxlen=WebSocketConfig.METRICS_MAX_TPS
            * 10
            * WebSocketConfig.METRICS_WINDOW_SECONDS
        )  # 수신자는 보통 이벤트보다 많으므로 10배 여유

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

        # Peak 연결 수 업데이트
        current_conn = len(self.active_connections)
        if current_conn > self._peak_connections:
            self._peak_connections = current_conn

        logger.info(
            f"WebSocket Client Connected: {context}. "
            f"Active connections: {current_conn}"
        )

    async def disconnect(
        self,
        websocket: WebSocket,
        code: int = 1000,
        reason: Optional[str] = None,
        propagate_errors: bool = False,
    ):
        """클라이언트 연결 해제, 목록 제거 및 명시적 소켓 종료"""
        context = self.active_connections.pop(websocket, None)

        if context:
            logger.info(
                f"WebSocket Client Removed: {context} (Code: {code}, Reason: {reason or 'none'}). "
                f"Active connections: {len(self.active_connections)}"
            )

        try:
            # WebSocketState.DISCONNECTED(2) 상수를 사용하여 상태 체크 (brittle-fix)
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=code, reason=reason)
        except Exception as exc:
            # Minimal log mostly for debug since connection might be already closed
            logger.debug("WebSocket close skipped/failed", exc_info=exc)
            if propagate_errors:
                raise

    async def _prune_connection(self, websocket: WebSocket) -> None:
        """[Helper] Dead Connection 정리 (간소화됨)"""
        try:
            await self.disconnect(websocket, propagate_errors=True)
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

    def get_metrics(self) -> Dict[str, Any]:
        """현재 시스템 메트릭 산출"""
        current_time = time.time()
        uptime = current_time - self._start_time

        # Broadcast TPS (이벤트 단위)
        window = WebSocketConfig.METRICS_WINDOW_SECONDS
        while (
            self._broadcast_timestamps
            and self._broadcast_timestamps[0] < current_time - window
        ):
            self._broadcast_timestamps.popleft()
        broadcast_tps = len(self._broadcast_timestamps) / float(window)

        # Message TPS (수신자 단위)
        while (
            self._message_timestamps
            and self._message_timestamps[0] < current_time - window
        ):
            self._message_timestamps.popleft()
        message_tps = len(self._message_timestamps) / float(window)

        return {
            "uptime_seconds": round(uptime, 2),
            "active_connections": len(self.active_connections),
            "peak_connections": self._peak_connections,
            "total_broadcasts": self._total_broadcasts_sent,
            "total_messages": self._total_messages_sent,
            "total_bytes": self._total_bytes_sent,
            "broadcast_tps": round(broadcast_tps, 2),
            "message_tps": round(message_tps, 2),
        }

    async def _local_broadcast(self, message: str):
        """[Internal] 실제 로컬 연결된 클라이언트들에게 메시지 전송 및 정리"""
        # 메시지 압축 처리
        processed_data, is_compressed = compress_payload(message)

        failed_connections: List[WebSocket] = []
        active_sockets = list(self.active_connections.keys())

        # 인코딩 한 번만 수행 (최적화)
        encoded_data = None
        if not is_compressed:
            encoded_data = processed_data.encode("utf-8")
            data_size = len(encoded_data)
        else:
            data_size = len(processed_data)

        async def _send_to_connection(connection: WebSocket) -> None:
            try:
                if is_compressed:
                    # 압축된 경우 Binary 데이터로 전송 (클라이언트에서 해제 필요)
                    await connection.send_bytes(processed_data)
                else:
                    # 압축되지 않은 경우 일반 Text로 전송
                    await connection.send_text(processed_data)

                # [Metrics] 개별 전송 지표 업데이트
                self._total_messages_sent += 1
                self._total_bytes_sent += data_size
                self._message_timestamps.append(time.time())

            except Exception as e:
                # Log context for better observability
                context = self.active_connections.get(connection)
                user_str = f"User({context.user_id})" if context else "Unknown"
                logger.error(f"Failed to broadcast to {user_str}: {e}")
                failed_connections.append(connection)

        # 각 연결에 대한 전송을 동시에 수행하여 느린 클라이언트가 전체 브로드캐스트를 지연시키지 않도록 함
        if active_sockets:
            await asyncio.gather(
                *(_send_to_connection(conn) for conn in active_sockets),
                return_exceptions=True,
            )

        # [Metrics] 브로드캐스트 이벤트 단위 지표 및 TPS 업데이트
        self._total_broadcasts_sent += 1
        self._broadcast_timestamps.append(time.time())

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
# backend/services/websocket_manager.py

import asyncio
import logging
import time
from collections import Counter, deque
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from starlette.websockets import WebSocketState
from backend.services.redis_pubsub import redis_broadcaster
from backend.services.compression_service import compress_payload
from backend.config import WebSocketConfig

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

        # [Metrics] 실시간 관측성 강화를 위한 지표 변수
        self._start_time = time.time()
        self._total_messages_sent = 0
        self._total_broadcasts_sent = 0  # [Metrics] 브로드캐스트 이벤트 단위 지표
        self._total_bytes_sent = 0
        self._peak_connections = 0

        # [Metrics] TPS 산출을 위한 샘플링 (설정 기반 상한 설정)
        # 1. 브로드캐스트 이벤트 단위 (Broadcast TPS)
        self._broadcast_timestamps = deque(
            maxlen=WebSocketConfig.METRICS_MAX_TPS
            * WebSocketConfig.METRICS_WINDOW_SECONDS
        )
        # 2. 개별 수신자 발송 단위 (Message/Recipient TPS)
        self._message_timestamps = deque(
            maxlen=WebSocketConfig.METRICS_MAX_TPS
            * 10
            * WebSocketConfig.METRICS_WINDOW_SECONDS
        )  # 수신자는 보통 이벤트보다 많으므로 10배 여유

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

        # Peak 연결 수 업데이트
        current_conn = len(self.active_connections)
        if current_conn > self._peak_connections:
            self._peak_connections = current_conn

        logger.info(
            f"WebSocket Client Connected: {context}. "
            f"Active connections: {current_conn}"
        )

    async def disconnect(
        self, websocket: WebSocket, code: int = 1000, reason: Optional[str] = None
    ):
        """클라이언트 연결 해제, 목록 제거 및 명시적 소켓 종료"""
        context = self.active_connections.pop(websocket, None)

        if context:
            logger.info(
                f"WebSocket Client Removed: {context} (Code: {code}, Reason: {reason or 'none'}). "
                f"Active connections: {len(self.active_connections)}"
            )

        try:
            # WebSocketState.DISCONNECTED(2) 상수를 사용하여 상태 체크 (brittle-fix)
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=code, reason=reason)
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

    def get_metrics(self) -> Dict[str, Any]:
        """현재 시스템 메트릭 산출"""
        current_time = time.time()
        uptime = current_time - self._start_time

        # Broadcast TPS (이벤트 단위)
        window = WebSocketConfig.METRICS_WINDOW_SECONDS
        while (
            self._broadcast_timestamps
            and self._broadcast_timestamps[0] < current_time - window
        ):
            self._broadcast_timestamps.popleft()
        broadcast_tps = len(self._broadcast_timestamps) / float(window)

        # Message TPS (수신자 단위)
        while (
            self._message_timestamps
            and self._message_timestamps[0] < current_time - window
        ):
            self._message_timestamps.popleft()
        message_tps = len(self._message_timestamps) / float(window)

        return {
            "uptime_seconds": round(uptime, 2),
            "active_connections": len(self.active_connections),
            "peak_connections": self._peak_connections,
            "total_broadcasts": self._total_broadcasts_sent,
            "total_messages": self._total_messages_sent,
            "total_bytes": self._total_bytes_sent,
            "broadcast_tps": round(broadcast_tps, 2),
            "message_tps": round(message_tps, 2),
        }

    async def _local_broadcast(self, message: str):
        """[Internal] 실제 로컬 연결된 클라이언트들에게 메시지 전송 및 정리"""
        # 메시지 압축 처리
        processed_data, is_compressed = compress_payload(message)

        failed_connections: List[WebSocket] = []
        active_sockets = list(self.active_connections.keys())

        for connection in active_sockets:
            try:
                if is_compressed:
                    # 압축된 경우 Binary 데이터로 전송 (클라이언트에서 해제 필요)
                    await connection.send_bytes(processed_data)
                    data_size = len(processed_data)
                else:
                    # 압축되지 않은 경우 일반 Text로 전송
                    await connection.send_text(processed_data)
                    data_size = len(processed_data.encode("utf-8"))

                # [Metrics] 개별 전송 지표 업데이트
                self._total_messages_sent += 1
                self._total_bytes_sent += data_size
                self._message_timestamps.append(time.time())

            except Exception as e:
                # Log context for better observability
                context = self.active_connections.get(connection)
                user_str = f"User({context.user_id})" if context else "Unknown"
                logger.error(f"Failed to broadcast to {user_str}: {e}")
                failed_connections.append(connection)

        # [Metrics] 브로드캐스트 이벤트 단위 지표 및 TPS 업데이트
        self._total_broadcasts_sent += 1
        self._broadcast_timestamps.append(time.time())

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

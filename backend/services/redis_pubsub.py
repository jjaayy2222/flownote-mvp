# backend/services/redis_pubsub.py

import asyncio
import logging
from typing import Optional, Callable, Awaitable
import redis.asyncio as redis
from backend.config import RedisConfig

logger = logging.getLogger(__name__)


class RedisPubSub:
    """
    Redis Pub/Sub 관리자 (Low-level)
    - Redis 연결 관리 (Connect/Disconnect)
    - 채널 구독 및 메시지 발행 직접 수행
    """

    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None

    async def connect(self):
        """Redis 연결 수립 (Lazy Initialization 지원)"""
        if not self.redis:
            try:
                self.redis = redis.from_url(
                    RedisConfig.REDIS_URL, decode_responses=True
                )
                # 연결 테스트 ping
                await self.redis.ping()
                logger.info(f"Connected to Redis at {RedisConfig.REDIS_URL}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.redis = None  # 연결 실패 시 None 유지
                raise

    async def disconnect(self):
        """리소스 정리 및 연결 종료"""
        if self.pubsub:
            await self.pubsub.close()
            self.pubsub = None  # [Fix] Reset reference to prevent stale usage

        if self.redis:
            await self.redis.close()
            self.redis = None  # [Fix] Reset reference
            logger.info("Disconnected from Redis")

    async def publish(self, channel: str, message: str):
        """Redis 채널에 메시지 발행"""
        if not self.redis:
            await self.connect()

        if self.redis:
            await self.redis.publish(channel, message)

    async def subscribe(self, channel: str, callback: Callable[[str], Awaitable[None]]):
        """
        특정 채널을 구독하고, 수신된 메시지를 콜백 함수로 전달하는 리스너 루프 실행
        Note: 이 메서드는 무한 루프를 돌므로, asyncio task로 실행해야 함.
        """
        if not self.redis:
            await self.connect()

        if self.redis:
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe(channel)
            logger.info(f"Subscribed to Redis channel: {channel}")

            try:
                async for message in self.pubsub.listen():
                    if message["type"] == "message":
                        await callback(message["data"])
            except asyncio.CancelledError:
                logger.info("Redis listener task cancelled.")
                raise
            except Exception as e:
                logger.error(f"Error in Redis listener loop: {e}", exc_info=True)


class RedisBroadcaster:
    """
    ConnectionManager를 위한 Redis 오케스트레이션 레이어 (High-level)
    - Redis Task 관리
    - 연결 실패 시 로컬 Fallback 처리
    - WebSocket Manager의 복잡성 제거
    """

    def __init__(self, client: RedisPubSub):
        self._client = client
        self._task: Optional[asyncio.Task] = None

    async def start(self, channel: str, handler: Callable[[str], Awaitable[None]]):
        """Connect + start subscribe listener task."""
        try:
            await self._client.connect()
            self._task = asyncio.create_task(self._client.subscribe(channel, handler))
            logger.info(f"RedisBroadcaster listening on channel: {channel}")
        except Exception as e:
            logger.warning(
                f"Redis initialization failed ({e}). Falling back to local mode."
            )

    async def stop(self):
        """Cancel subscribe task + disconnect, best-effort."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        await self._client.disconnect()

    async def publish_or_fallback(
        self, channel: str, message: str, fallback: Callable[[str], Awaitable[None]]
    ):
        """Publish if Redis is available, otherwise call fallback."""
        if self._client.redis:
            try:
                await self._client.publish(channel, message)
                return
            except Exception as e:
                logger.error(
                    f"Redis publish failed: {e}. Falling back to local broadcast."
                )
        # Fallback to local broadcast if Redis is unavailable or failed
        await fallback(message)


# 전역 인스턴스
redis_client = RedisPubSub()
redis_broadcaster = RedisBroadcaster(redis_client)

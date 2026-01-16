# backend/services/redis_pubsub.py

import asyncio
import logging
from typing import Optional, Callable, Awaitable
import redis.asyncio as redis
from backend.config import RedisConfig

logger = logging.getLogger(__name__)


class RedisPubSub:
    """
    Redis Pub/Sub 관리자
    - Redis 연결 초기화 및 관리
    - 채널별 구독 및 비동기 메시지 수신 루프 실행
    - 시스템 전역 메시지 발행
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
        if self.redis:
            await self.redis.close()
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
                # 에러 발생 후 재연결 로직은 Phase 2 과제 (현재는 종료)


# 전역 인스턴스
redis_client = RedisPubSub()

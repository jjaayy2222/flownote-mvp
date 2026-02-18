from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING

# Type Checking Only Imports
if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

from langgraph.checkpoint.memory import MemorySaver

# 로거 설정
logger = logging.getLogger(__name__)

try:
    # Redis Checkpointer 의존성 확인 (Optional)
    # 실제 사용 시: pip install langgraph-checkpoint-redis
    # ShallowRedisSaver: RedisJSON 모듈 없이 동작하는 경량 버전 (기본 Redis 호환)
    # RedisSaver: RedisJSON 모듈 필요 (고급 기능 지원)
    from langgraph.checkpoint.redis import ShallowRedisSaver

    _REDIS_AVAILABLE = True
except ImportError:
    ShallowRedisSaver = None
    _REDIS_AVAILABLE = False


def get_checkpointer() -> BaseCheckpointSaver:
    """
    Checkpointer 인스턴스를 반환하는 팩토리 함수.

    우선순위:
    1. Redis (REDIS_URL 환경변수 존재 + 의존성 설치됨)
       - ShallowRedisSaver 사용 (기본 Redis 호환, RedisJSON 불필요)
    2. Memory (In-Memory, 개발용 기본값)

    Returns:
        BaseCheckpointSaver: 컴파일 시 사용할 체크포인터
    """
    redis_url = os.getenv("REDIS_URL")

    if redis_url and _REDIS_AVAILABLE:
        try:
            # ShallowRedisSaver: 기본 Redis 명령어만 사용 (JSON.SET 불필요)
            # Security Fix: Do not log sensitive REDIS_URL
            checkpointer = ShallowRedisSaver(redis_url=redis_url)
            logger.info(
                "Initialized ShallowRedisSaver (Redis Checkpointer) successfully."
            )
            return checkpointer

        except Exception:
            logger.error(
                "Failed to initialize Redis Checkpointer. Falling back to MemorySaver.",
                exc_info=True,
            )
            return MemorySaver()

    if redis_url and not _REDIS_AVAILABLE:
        logger.warning(
            "REDIS_URL is set but 'langgraph-checkpoint-redis' is not installed. "
            "Falling back to MemorySaver. "
            "To enable Redis persistence, run: pip install langgraph-checkpoint-redis"
        )

    logger.info(
        "Using MemorySaver (In-Memory Checkpointer). State will be lost on restart."
    )
    return MemorySaver()

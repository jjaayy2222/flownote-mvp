import os
import logging
from typing import Optional, TYPE_CHECKING

# Type Checking Only Imports
# LangGraph는 필수 의존성이므로 명시적으로 임포트하여 타입 힌트 지원
if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

from langgraph.checkpoint.memory import MemorySaver

# 로거 설정
logger = logging.getLogger(__name__)

try:
    # Redis Checkpointer 의존성 확인 (Optional)
    # 실제 사용 시: pip install langgraph-checkpoint-redis
    from langgraph.checkpoint.redis import RedisSaver
    from redis import Redis
except ImportError:
    RedisSaver = None
    Redis = None


def get_checkpointer() -> "BaseCheckpointSaver":
    """
    Checkpointer 인스턴스를 반환하는 팩토리 함수.

    우선순위:
    1. Redis (REDIS_URL 환경변수 존재 + 의존성 설치됨)
    2. Memory (In-Memory, 개발용 기본값)

    Returns:
        BaseCheckpointSaver: 컴파일 시 사용할 체크포인터
    """
    redis_url = os.getenv("REDIS_URL")

    if redis_url and RedisSaver:
        try:
            # Redis 연결 설정
            connection = Redis.from_url(redis_url)
            checkpointer = RedisSaver(connection)

            # Security Fix: Do not log sensitive REDIS_URL
            logger.info("Initialized Redis Checkpointer successfully.")
            return checkpointer

        except Exception as e:
            logger.error(
                "Failed to initialize Redis Checkpointer. Falling back to MemorySaver.",
                exc_info=True,
            )
            return MemorySaver()

    if redis_url and not RedisSaver:
        logger.warning(
            "REDIS_URL is set but 'langgraph-checkpoint-redis' or 'redis' is not installed. Using MemorySaver."
        )

    logger.info(
        "Using MemorySaver (In-Memory Checkpointer). State will be lost on restart."
    )
    return MemorySaver()

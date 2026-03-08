# backend/services/chat_history_service.py

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.services.redis_pubsub import redis_client
from backend.api.models import ChatMessage

logger = logging.getLogger(__name__)


class ChatHistoryService:
    """Redis 기반 채팅 히스토리 관리 서비스"""

    def __init__(self, ttl: int = 86400 * 7):  # 기본 7일 유지
        self.ttl = ttl

    def _get_key(self, session_id: str) -> str:
        return f"chat:history:{session_id}"

    async def add_message(self, session_id: str, role: str, content: str):
        """메시지를 Redis 리스트에 추가"""
        if not session_id or not session_id.strip():
            logger.error("Operation failed: session_id is missing or empty.")
            raise ValueError("session_id is required to add messages to history.")

        if not redis_client.is_connected():
            try:
                await redis_client.connect()
            except Exception as e:
                logger.error(
                    "Redis connection failed in ChatHistoryService",
                    extra={"session_id": session_id, "error": str(e)},
                )
                return

        key = self._get_key(session_id)
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # 리스트 끝에 추가
            await redis_client.redis.rpush(key, json.dumps(message))
            # 만료 시간 갱신
            await redis_client.redis.expire(key, self.ttl)
        except Exception as e:
            logger.error(
                "Failed to add message to history",
                extra={"session_id": session_id, "error": str(e)},
            )

    async def get_history(self, session_id: str, limit: int = 20) -> List[ChatMessage]:
        """최근 대화 내역 조회"""
        if not session_id or not session_id.strip():
            logger.error("Operation failed: session_id is missing or empty.")
            raise ValueError("session_id is required to get chat history.")

        if not redis_client.is_connected():
            try:
                await redis_client.connect()
            except Exception as e:
                logger.error(
                    "Redis connection failed in ChatHistoryService",
                    extra={"session_id": session_id, "error": str(e)},
                )
                return []

        key = self._get_key(session_id)
        try:
            # 최근 limit개의 메시지 가져오기 (리스트의 끝에서부터)
            data = await redis_client.redis.lrange(key, -limit, -1)
            messages = []
            for item in data:
                msg_dict = json.loads(item)
                messages.append(ChatMessage(**msg_dict))
            return messages
        except Exception as e:
            logger.error(
                "Failed to get history",
                extra={"session_id": session_id, "error": str(e)},
            )
            return []

    async def clear_history(self, session_id: str):
        """특정 세션의 히스토리 삭제"""
        if not session_id or not session_id.strip():
            logger.error("Operation failed: session_id is missing or empty.")
            raise ValueError("session_id is required to clear history.")

        if not redis_client.is_connected():
            try:
                await redis_client.connect()
            except Exception as e:
                logger.error(
                    "Failed to connect to Redis for clearing history",
                    extra={"session_id": session_id, "error": str(e)},
                )
                return

        key = self._get_key(session_id)
        try:
            await redis_client.redis.delete(key)
        except Exception as e:
            logger.error(
                "Failed to clear history",
                extra={"session_id": session_id, "error": str(e)},
            )


def get_chat_history_service() -> ChatHistoryService:
    return ChatHistoryService()

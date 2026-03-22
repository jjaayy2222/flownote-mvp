# backend/services/chat_history_service.py

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.services.redis_pubsub import redis_client
from backend.api.models import ChatMessage

logger = logging.getLogger(__name__)

# Redis 키 프리픽스 상수
_HISTORY_PREFIX = "chat:history:"
_SESSION_META_PREFIX = "chat:session:meta:"
_USER_SESSIONS_PREFIX = "chat:user:sessions:"


class ChatHistoryService:
    """Redis 기반 채팅 히스토리 및 세션 관리 서비스"""

    def __init__(self, ttl: int = 86400 * 7):  # 기본 7일 유지
        self.ttl = ttl

    def _history_key(self, session_id: str) -> str:
        return f"{_HISTORY_PREFIX}{session_id}"

    def _session_meta_key(self, session_id: str) -> str:
        return f"{_SESSION_META_PREFIX}{session_id}"

    def _user_sessions_key(self, user_id: str) -> str:
        return f"{_USER_SESSIONS_PREFIX}{user_id}"

    async def _ensure_connected(self, context: str) -> bool:
        """Redis 연결 보장 헬퍼. 연결 실패 시 False 반환."""
        if not redis_client.is_connected():
            try:
                await redis_client.connect()
            except Exception as e:
                logger.error(
                    "Redis connection failed in ChatHistoryService [%s]",
                    context,
                    extra={"error": str(e)},
                )
                return False
        return True

    async def register_session(
        self,
        session_id: str,
        user_id: str,
        name: Optional[str] = None,
        preview: Optional[str] = None,
    ) -> None:
        """세션 메타데이터를 Redis에 등록하거나 갱신한다."""
        if not session_id or not user_id:
            raise ValueError("session_id and user_id are required.")

        if not await self._ensure_connected("register_session"):
            return

        now = datetime.now().isoformat()
        meta_key = self._session_meta_key(session_id)

        try:
            # 기존 메타가 있으면 created_at 유지, 없으면 현재 시각 사용
            existing_raw = await redis_client.redis.get(meta_key)
            created_at = now
            if existing_raw:
                existing = json.loads(existing_raw)
                created_at = existing.get("created_at", now)

            meta = {
                "session_id": session_id,
                "user_id": user_id,
                "name": name,
                "created_at": created_at,
                "last_active_at": now,
                "preview": preview,
            }
            await redis_client.redis.set(meta_key, json.dumps(meta, ensure_ascii=False))
            await redis_client.redis.expire(meta_key, self.ttl)

            # User → Session 역색인: Sorted Set (score = timestamp)
            score = datetime.now().timestamp()
            user_sessions_key = self._user_sessions_key(user_id)
            await redis_client.redis.zadd(user_sessions_key, {session_id: score})
            await redis_client.redis.expire(user_sessions_key, self.ttl)

        except Exception as e:
            logger.error(
                "Failed to register session",
                extra={"session_id": session_id, "error": str(e)},
            )

    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """사용자의 세션 목록을 최근 활성순으로 반환한다."""
        if not user_id:
            raise ValueError("user_id is required.")

        if not await self._ensure_connected("list_sessions"):
            return []

        try:
            user_sessions_key = self._user_sessions_key(user_id)
            # Sorted Set에서 score(timestamp) 내림차순 조회
            session_ids = await redis_client.redis.zrevrange(user_sessions_key, 0, -1)
            sessions = []
            for sid in session_ids:
                meta_key = self._session_meta_key(sid)
                raw = await redis_client.redis.get(meta_key)
                if raw:
                    sessions.append(json.loads(raw))
            return sessions
        except Exception as e:
            logger.error(
                "Failed to list sessions",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def rename_session(self, session_id: str, name: str) -> bool:
        """세션 이름을 수정한다. 세션이 없으면 False 반환."""
        if not session_id or not name:
            raise ValueError("session_id and name are required.")

        if not await self._ensure_connected("rename_session"):
            return False

        meta_key = self._session_meta_key(session_id)
        try:
            raw = await redis_client.redis.get(meta_key)
            if not raw:
                return False
            meta = json.loads(raw)
            meta["name"] = name
            await redis_client.redis.set(meta_key, json.dumps(meta, ensure_ascii=False))
            await redis_client.redis.expire(meta_key, self.ttl)
            return True
        except Exception as e:
            logger.error(
                "Failed to rename session",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False

    async def add_message(self, session_id: str, role: str, content: str):
        """메시지를 Redis 리스트에 추가하고 세션 미리보기를 갱신한다."""
        if not session_id or not session_id.strip():
            logger.error("Operation failed: session_id is missing or empty.")
            raise ValueError("session_id is required to add messages to history.")

        if not await self._ensure_connected("add_message"):
            return

        key = self._history_key(session_id)
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            await redis_client.redis.rpush(key, json.dumps(message))
            await redis_client.redis.expire(key, self.ttl)

            # 세션 메타 존재 시 preview 및 last_active_at 갱신
            meta_key = self._session_meta_key(session_id)
            raw = await redis_client.redis.get(meta_key)
            if raw:
                meta = json.loads(raw)
                meta["last_active_at"] = datetime.now().isoformat()
                meta["preview"] = content[:80] if content else None
                await redis_client.redis.set(
                    meta_key, json.dumps(meta, ensure_ascii=False)
                )
                await redis_client.redis.expire(meta_key, self.ttl)

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

        if not await self._ensure_connected("get_history"):
            return []

        key = self._history_key(session_id)
        try:
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

        if not await self._ensure_connected("clear_history"):
            return

        key = self._history_key(session_id)
        try:
            await redis_client.redis.delete(key)
        except Exception as e:
            logger.error(
                "Failed to clear history",
                extra={"session_id": session_id, "error": str(e)},
            )


def get_chat_history_service() -> ChatHistoryService:
    return ChatHistoryService()

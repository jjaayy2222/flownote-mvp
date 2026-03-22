# backend/services/chat_history_service.py

import hashlib
import json
import logging
from json import JSONDecodeError
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from backend.services.redis_pubsub import redis_client
from backend.api.models import ChatMessage

logger = logging.getLogger(__name__)

# Redis 키 프리픽스 상수
_HISTORY_PREFIX = "chat:history:"
_SESSION_META_PREFIX = "chat:session:meta:"
_USER_SESSIONS_PREFIX = "chat:user:sessions:"

# preview 최대 길이 (하드코딩 방지)
_PREVIEW_MAX_LEN = 80


def _now_utc() -> datetime:
    """항상 UTC timezone-aware datetime을 반환하는 중앙 헬퍼."""
    return datetime.now(timezone.utc)


def _mask_id(value: str) -> str:
    """민감 ID를 SHA-256 앞 12자리로 마스킹하여 로그에 안전하게 기록."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]


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
                logger.exception(
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
        """세션 메타데이터를 Redis에 등록하거나 갱신한다.

        동일 session_id로 재호출 시 created_at은 최초값을 유지하고
        last_active_at과 Sorted Set score만 갱신된다.
        """
        if not session_id or not user_id:
            raise ValueError("session_id and user_id are required.")

        if not await self._ensure_connected("register_session"):
            return

        # 단일 now 객체로 ISO string과 ZSET score를 동시에 파생 → drift 제거
        now = _now_utc()
        now_iso = now.isoformat()
        now_score = now.timestamp()

        meta_key = self._session_meta_key(session_id)

        try:
            # 기존 메타가 있으면 created_at 유지, 없으면 현재 시각 사용
            existing_raw = await redis_client.redis.get(meta_key)
            created_at = now_iso
            if existing_raw:
                try:
                    existing = json.loads(existing_raw)
                    if not isinstance(existing, dict):
                        raise ValueError("Corrupted session meta: not a dict")
                    created_at = existing.get("created_at", now_iso)
                except (JSONDecodeError, ValueError) as e:
                    logger.error(
                        "Failed to parse existing session meta, resetting.",
                        extra={"session_id_hash": _mask_id(session_id), "error": str(e)},
                    )

            meta: Dict[str, Any] = {
                "session_id": session_id,
                "user_id": user_id,
                "name": name,
                "created_at": created_at,
                "last_active_at": now_iso,
                "preview": preview,
            }
            await redis_client.redis.set(meta_key, json.dumps(meta, ensure_ascii=False))
            await redis_client.redis.expire(meta_key, self.ttl)

            # User → Session 역색인: Sorted Set (score = UTC timestamp)
            user_sessions_key = self._user_sessions_key(user_id)
            await redis_client.redis.zadd(user_sessions_key, {session_id: now_score})
            await redis_client.redis.expire(user_sessions_key, self.ttl)

        except Exception as e:
            logger.exception(
                "Failed to register session",
                extra={"session_id_hash": _mask_id(session_id), "error": str(e)},
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
            # decode_responses=True 환경에서도 str() 보장 (방어적 처리)
            raw_ids = await redis_client.redis.zrevrange(user_sessions_key, 0, -1)
            sessions = []
            for raw_sid in raw_ids:
                sid = str(raw_sid)  # bytes 방어: decode_responses 설정 변경에도 안전
                meta_key = self._session_meta_key(sid)
                raw = await redis_client.redis.get(meta_key)
                if not raw:
                    continue
                try:
                    meta = json.loads(raw)
                    if not isinstance(meta, dict):
                        raise ValueError("Corrupted meta: not a dict")
                    sessions.append(meta)
                except (JSONDecodeError, ValueError) as e:
                    logger.error(
                        "Skipping malformed session meta during listing.",
                        extra={"session_id_hash": _mask_id(sid), "error": str(e)},
                    )
            return sessions
        except Exception as e:
            logger.exception(
                "Failed to list sessions",
                extra={"user_id_hash": _mask_id(user_id), "error": str(e)},
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
            try:
                meta = json.loads(raw)
                if not isinstance(meta, dict):
                    raise ValueError("Corrupted meta: not a dict")
            except (JSONDecodeError, ValueError) as e:
                logger.error(
                    "Failed to parse session meta on rename.",
                    extra={"session_id_hash": _mask_id(session_id), "error": str(e)},
                )
                return False

            meta["name"] = name
            await redis_client.redis.set(meta_key, json.dumps(meta, ensure_ascii=False))
            await redis_client.redis.expire(meta_key, self.ttl)
            return True
        except Exception as e:
            logger.exception(
                "Failed to rename session",
                extra={"session_id_hash": _mask_id(session_id), "error": str(e)},
            )
            return False

    async def add_message(self, session_id: str, role: str, content: str):
        """메시지를 Redis 리스트에 추가하고 세션 미리보기를 갱신한다."""
        if not session_id or not session_id.strip():
            logger.error("Operation failed: session_id is missing or empty.")
            raise ValueError("session_id is required to add messages to history.")

        if not await self._ensure_connected("add_message"):
            return

        now = _now_utc()
        key = self._history_key(session_id)
        message: Dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": now.isoformat(),
        }

        try:
            await redis_client.redis.rpush(key, json.dumps(message))
            await redis_client.redis.expire(key, self.ttl)

            # 세션 메타 존재 시 preview 및 last_active_at 갱신
            meta_key = self._session_meta_key(session_id)
            raw = await redis_client.redis.get(meta_key)
            if raw:
                try:
                    meta = json.loads(raw)
                    if not isinstance(meta, dict):
                        raise ValueError("Corrupted meta: not a dict")
                    meta["last_active_at"] = now.isoformat()
                    meta["preview"] = content[:_PREVIEW_MAX_LEN] if content else None
                    await redis_client.redis.set(
                        meta_key, json.dumps(meta, ensure_ascii=False)
                    )
                    await redis_client.redis.expire(meta_key, self.ttl)
                except (JSONDecodeError, ValueError) as e:
                    logger.error(
                        "Failed to update session preview on add_message.",
                        extra={"session_id_hash": _mask_id(session_id), "error": str(e)},
                    )

        except Exception as e:
            logger.exception(
                "Failed to add message to history",
                extra={"session_id_hash": _mask_id(session_id), "error": str(e)},
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
            parse_errors = 0
            for item in data:
                try:
                    msg_dict = json.loads(item)
                    if not isinstance(msg_dict, dict):
                        parse_errors += 1
                        continue
                    messages.append(ChatMessage(**msg_dict))
                except (JSONDecodeError, TypeError):
                    parse_errors += 1
            if parse_errors:
                logger.error(
                    "Skipped malformed messages during get_history.",
                    extra={
                        "session_id_hash": _mask_id(session_id),
                        "skipped_count": parse_errors,
                    },
                )
            return messages
        except Exception as e:
            logger.exception(
                "Failed to get history",
                extra={"session_id_hash": _mask_id(session_id), "error": str(e)},
            )
            return []

    async def clear_history(self, session_id: str, user_id: Optional[str] = None):
        """특정 세션의 히스토리 + 메타 + ZSET 역색인을 완전 삭제한다.

        user_id가 제공된 경우 사용자의 Sorted Set에서 해당 session_id도 제거한다.
        user_id가 없으면 히스토리와 메타만 삭제되고 ZSET 항목은 잔류할 수 있다.
        완전 정리를 보장하려면 호출 측에서 user_id를 함께 전달하는 것을 권장한다.
        """
        if not session_id or not session_id.strip():
            logger.error("Operation failed: session_id is missing or empty.")
            raise ValueError("session_id is required to clear history.")

        if not await self._ensure_connected("clear_history"):
            return

        history_key = self._history_key(session_id)
        meta_key = self._session_meta_key(session_id)
        try:
            # 히스토리 삭제
            await redis_client.redis.delete(history_key)
            # 세션 메타 삭제
            await redis_client.redis.delete(meta_key)
            # ZSET 역색인 제거 (user_id 알 수 있을 때만)
            if user_id:
                user_sessions_key = self._user_sessions_key(user_id)
                await redis_client.redis.zrem(user_sessions_key, session_id)
        except Exception as e:
            logger.exception(
                "Failed to clear history",
                extra={"session_id_hash": _mask_id(session_id), "error": str(e)},
            )


def get_chat_history_service() -> ChatHistoryService:
    return ChatHistoryService()

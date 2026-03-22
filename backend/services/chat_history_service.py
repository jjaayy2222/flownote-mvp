# backend/services/chat_history_service.py

import hashlib
import json
import logging
from functools import wraps
from json import JSONDecodeError
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, timezone
from backend.services.redis_pubsub import redis_client
from backend.api.models import ChatMessage

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Redis 키 프리픽스 상수
# ─────────────────────────────────────────────────────────────
_HISTORY_PREFIX = "chat:history:"
_SESSION_META_PREFIX = "chat:session:meta:"
_USER_SESSIONS_PREFIX = "chat:user:sessions:"

# preview 최대 길이 (하드코딩 방지)
_PREVIEW_MAX_LEN = 80


# ─────────────────────────────────────────────────────────────
# 커스텀 예외
# ─────────────────────────────────────────────────────────────
class RedisUnavailableError(RuntimeError):
    """Redis 연결 불가 시 발생. 전역 예외 핸들러에서 503으로 변환된다."""


# ─────────────────────────────────────────────────────────────
# 모듈 레벨 순수 헬퍼 함수
# ─────────────────────────────────────────────────────────────
def _now_utc() -> datetime:
    """항상 UTC timezone-aware datetime을 반환하는 중앙 헬퍼."""
    return datetime.now(timezone.utc)


def _mask_id(value: str) -> str:
    """민감 ID를 SHA-256 앞 12자리로 마스킹하여 로그에 안전하게 기록."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────
# 로깅·재전파 데코레이터
# ─────────────────────────────────────────────────────────────
def _log_and_reraise(
    log_message: str,
    extra_builder: Callable[..., Dict[str, Any]],
):
    """공개 메서드용 데코레이터.

    - RedisUnavailableError: 이미 _ensure_connected에서 로깅됨.
      중복 로깅 없이 그대로 다시 던진다.
    - 그 외 예외: log_message와 extra_builder로 구성한 컨텍스트를
      logger.exception()으로 기록한 뒤 다시 던진다.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return await func(self, *args, **kwargs)
            except RedisUnavailableError:
                raise  # 이미 로깅됨, 중복 로깅 방지
            except Exception as e:
                logger.exception(
                    log_message,
                    extra=extra_builder(e, *args, **kwargs),
                )
                raise

        return wrapper

    return decorator


class ChatHistoryService:
    """Redis 기반 채팅 히스토리 및 세션 관리 서비스.

    Redis 연결 불가 시 RedisUnavailableError를 발생시켜 상위 계층이
    적절한 5xx 응답을 반환하도록 Fail-Fast 원칙을 따릅니다.
    """

    def __init__(self, ttl: int = 86400 * 7):  # 기본 7일 유지
        self.ttl = ttl

    # ── 키 팩토리 ───────────────────────────────────────────────
    def _history_key(self, session_id: str) -> str:
        return f"{_HISTORY_PREFIX}{session_id}"

    def _session_meta_key(self, session_id: str) -> str:
        return f"{_SESSION_META_PREFIX}{session_id}"

    def _user_sessions_key(self, user_id: str) -> str:
        return f"{_USER_SESSIONS_PREFIX}{user_id}"

    # ── 저수준 내부 헬퍼 ───────────────────────────────────────

    async def _ensure_connected(self, context: str) -> None:
        """Redis 연결 보장 헬퍼.

        연결 실패 시 RedisUnavailableError를 raise하여 silent no-op를 방지한다.
        """
        if not redis_client.is_connected():
            try:
                await redis_client.connect()
            except Exception as e:
                logger.exception(
                    "Redis connection failed in ChatHistoryService [%s]",
                    context,
                    extra={"error": str(e)},
                )
                raise RedisUnavailableError(
                    f"Redis unavailable (context={context})"
                ) from e

    async def _load_json_dict(
        self,
        key: str,
        *,
        log_context: str,
        id_hash: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Redis 키에서 값을 읽어 JSON dict로 파싱하는 중앙 헬퍼.

        파싱 실패 또는 키 없을 때 None 반환. 예외·로그 정책을 단일화한다.
        """
        raw = await redis_client.redis.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("JSON value is not an object (dict)")
            return data
        except (JSONDecodeError, ValueError) as e:
            logger.error(
                "Malformed JSON at key during %s, ignoring.",
                log_context,
                extra={"key": key, "id_hash": id_hash, "error": str(e)},
            )
            return None

    def _parse_message(self, raw: Any) -> Optional[Dict[str, Any]]:
        """개별 히스토리 메시지 항목을 dict로 파싱하는 헬퍼."""
        try:
            msg = json.loads(raw)
            return msg if isinstance(msg, dict) else None
        except (JSONDecodeError, TypeError):
            return None

    async def _get_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """session_id에 해당하는 메타데이터 dict를 읽어 반환한다."""
        key = self._session_meta_key(session_id)
        return await self._load_json_dict(
            key,
            log_context="get_session_meta",
            id_hash=_mask_id(session_id),
        )

    async def _save_session_meta(self, session_id: str, meta: Dict[str, Any]) -> None:
        """메타데이터 dict를 Redis에 저장하고 TTL을 갱신한다."""
        key = self._session_meta_key(session_id)
        await redis_client.redis.set(key, json.dumps(meta, ensure_ascii=False))
        await redis_client.redis.expire(key, self.ttl)

    async def _touch_session(
        self,
        session_id: str,
        user_id: Optional[str],
        *,
        new_preview: Optional[str] = None,
        now: Optional[datetime] = None,
        force_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """세션 메타의 last_active_at·preview와 ZSET score를 단일 지점에서 갱신한다.

        force_meta가 제공된 경우 Redis 읽기를 건너뛰고 해당 dict를 그대로 저장한다.
        force_meta가 None인 경우 기존 메타를 읽어 last_active_at과 preview만 업데이트한다.

        user_id가 None이면 저장된 메타에서 복원하여 ZSET score도 갱신한다.
        """
        now = now or _now_utc()
        now_iso = now.isoformat()
        now_score = now.timestamp()

        if force_meta is not None:
            meta = force_meta
        else:
            meta = await self._get_session_meta(session_id) or {}

        # user_id 결정: 인자 우선, 없으면 메타에서 복원
        effective_user_id = user_id or meta.get("user_id")

        meta.setdefault("session_id", session_id)
        meta.setdefault("created_at", now_iso)
        meta["last_active_at"] = now_iso
        if new_preview is not None:
            meta["preview"] = new_preview[:_PREVIEW_MAX_LEN]

        await self._save_session_meta(session_id, meta)

        # ZSET score 갱신 (최근 활성 순 정렬 일관성 유지)
        if effective_user_id:
            user_sessions_key = self._user_sessions_key(effective_user_id)
            await redis_client.redis.zadd(user_sessions_key, {session_id: now_score})
            await redis_client.redis.expire(user_sessions_key, self.ttl)

    # ── 공개 API ───────────────────────────────────────────────

    @_log_and_reraise(
        "Failed to register session",
        lambda e, session_id, user_id, *args, **kwargs: {
            "session_id_hash": _mask_id(session_id),
            "error": str(e),
        },
    )
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

        Raises:
            ValueError: 필수 입력 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not user_id:
            raise ValueError("session_id and user_id are required.")

        await self._ensure_connected("register_session")

        now = _now_utc()

        # 기존 created_at 보존 (재등록 시에도 최초 생성 시각 유지)
        existing_meta = await self._get_session_meta(session_id)
        created_at = (
            existing_meta.get("created_at", now.isoformat())
            if existing_meta
            else now.isoformat()
        )

        # 전체 메타를 구성하여 _touch_session에 위임 (SSOT: ZSET 갱신 로직 단일화)
        force_meta: Dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "name": name,
            "created_at": created_at,
            "preview": preview,
        }
        await self._touch_session(
            session_id, user_id, now=now, force_meta=force_meta
        )

    @_log_and_reraise(
        "Failed to list sessions",
        lambda e, user_id, *args, **kwargs: {
            "user_id_hash": _mask_id(user_id),
            "error": str(e),
        },
    )
    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """사용자의 세션 목록을 최근 활성순으로 반환한다.

        보안: 메타의 user_id가 요청자와 일치하는 항목만 포함한다 (교차 유저 데이터 차단).

        Raises:
            ValueError: user_id 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not user_id:
            raise ValueError("user_id is required.")

        await self._ensure_connected("list_sessions")

        user_sessions_key = self._user_sessions_key(user_id)
        # str() 캐스팅: decode_responses 설정이 바뀌어도 방어적으로 str 보장
        raw_ids = await redis_client.redis.zrevrange(user_sessions_key, 0, -1)
        sessions: List[Dict[str, Any]] = []
        for raw_sid in raw_ids:
            sid = str(raw_sid)
            meta = await self._load_json_dict(
                self._session_meta_key(sid),
                log_context="list_sessions",
                id_hash=_mask_id(sid),
            )
            if meta is None:
                continue
            # 보안: ZSET 오염/재사용으로 인한 교차 유저 데이터 유출 방지
            if meta.get("user_id") != user_id:
                logger.warning(
                    "Cross-user session leakage detected and blocked.",
                    extra={
                        "user_id_hash": _mask_id(user_id),
                        "session_id_hash": _mask_id(sid),
                    },
                )
                continue
            sessions.append(meta)
        return sessions

    @_log_and_reraise(
        "Failed to rename session",
        lambda e, session_id, name, *args, **kwargs: {
            "session_id_hash": _mask_id(session_id),
            "error": str(e),
        },
    )
    async def rename_session(self, session_id: str, name: str) -> bool:
        """세션 이름을 수정한다. 세션이 없으면 False 반환.

        Raises:
            ValueError: 필수 입력 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not name:
            raise ValueError("session_id and name are required.")

        await self._ensure_connected("rename_session")

        meta = await self._get_session_meta(session_id)
        if meta is None:
            return False
        meta["name"] = name
        await self._save_session_meta(session_id, meta)
        return True

    @_log_and_reraise(
        "Failed to add message to history",
        lambda e, session_id, *args, **kwargs: {
            "session_id_hash": _mask_id(session_id),
            "error": str(e),
        },
    )
    async def add_message(self, session_id: str, role: str, content: str) -> None:
        """메시지를 Redis 리스트에 추가하고 세션 메타와 ZSET score를 갱신한다.

        Raises:
            ValueError: session_id 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id is required to add messages to history.")

        await self._ensure_connected("add_message")

        now = _now_utc()
        key = self._history_key(session_id)
        message: Dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": now.isoformat(),
        }

        await redis_client.redis.rpush(key, json.dumps(message))
        await redis_client.redis.expire(key, self.ttl)

        # 메타 preview + last_active_at + ZSET score를 단일 헬퍼로 갱신
        # user_id=None → _touch_session이 메타에서 user_id를 복원하여 ZSET도 업데이트
        await self._touch_session(
            session_id, user_id=None, new_preview=content, now=now
        )

    @_log_and_reraise(
        "Failed to get history",
        lambda e, session_id, *args, **kwargs: {
            "session_id_hash": _mask_id(session_id),
            "error": str(e),
        },
    )
    async def get_history(self, session_id: str, limit: int = 20) -> List[ChatMessage]:
        """최근 대화 내역 조회.

        Raises:
            ValueError: session_id 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id is required to get chat history.")

        await self._ensure_connected("get_history")

        key = self._history_key(session_id)
        data = await redis_client.redis.lrange(key, -limit, -1)
        messages: List[ChatMessage] = []
        parse_errors = 0
        for item in data:
            msg_dict = self._parse_message(item)
            if msg_dict is None:
                parse_errors += 1
                continue
            messages.append(ChatMessage(**msg_dict))
        if parse_errors:
            # 루프 내 개별 로깅 대신 요약 1회 출력 (로그 스팸 방지)
            logger.error(
                "Skipped malformed messages during get_history.",
                extra={
                    "session_id_hash": _mask_id(session_id),
                    "skipped_count": parse_errors,
                },
            )
        return messages

    @_log_and_reraise(
        "Failed to clear history",
        lambda e, session_id, *args, **kwargs: {
            "session_id_hash": _mask_id(session_id),
            "error": str(e),
        },
    )
    async def clear_history(self, session_id: str, user_id: Optional[str] = None) -> None:
        """특정 세션의 히스토리 + 메타 + ZSET 역색인을 완전 삭제한다.

        user_id가 없으면 메타에서 자동으로 복원하여 ZSET 항목도 제거한다.

        Raises:
            ValueError: session_id 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id is required to clear history.")

        await self._ensure_connected("clear_history")

        # user_id 미전달 시 메타에서 복원하여 ZSET도 완전 정리
        effective_user_id = user_id
        if not effective_user_id:
            meta = await self._get_session_meta(session_id)
            if meta:
                effective_user_id = meta.get("user_id")

        await redis_client.redis.delete(self._history_key(session_id))
        await redis_client.redis.delete(self._session_meta_key(session_id))

        if effective_user_id:
            user_sessions_key = self._user_sessions_key(effective_user_id)
            await redis_client.redis.zrem(user_sessions_key, session_id)


def get_chat_history_service() -> ChatHistoryService:
    return ChatHistoryService()

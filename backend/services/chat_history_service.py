# backend/services/chat_history_service.py

import hashlib
import json
import logging
from json import JSONDecodeError
from typing import Any, Dict, List, NoReturn, Optional
from datetime import datetime, timezone
from backend.services.redis_pubsub import redis_client  # type: ignore[import]
from backend.api.models import ChatMessage  # type: ignore[import]

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
    """Redis 연결 불가 시 발생. main.py의 전역 핸들러에서 503으로 변환된다."""


# ─────────────────────────────────────────────────────────────
# 모듈 레벨 순수 헬퍼 함수
# ─────────────────────────────────────────────────────────────
def _now_utc() -> datetime:
    """항상 UTC timezone-aware datetime을 반환하는 중앙 헬퍼."""
    return datetime.now(timezone.utc)


def _mask_id(value: str) -> str:
    """민감 ID를 SHA-256 앞 12자리로 마스킹하여 로그에 안전하게 기록.
    
    Checklist (Security): hashlib.sha256 사용으로 개인정보 보호.
    Checklist (Null Safety): value는 str 타입 힌트가 있으나 방어적으로 다룸.
    """
    if not value or not isinstance(value, str):
        return "invalid_id"
    return str(hashlib.sha256(value.encode()).hexdigest()[:12])  # type: ignore[index]


def _log_and_reraise_generic(
    message: str,
    extra: Dict[str, Any],
    exc: Exception,
) -> NoReturn:
    """예외 종류에 따라 선별적으로 로깅하고 재전파한다.

    - RedisUnavailableError: _ensure_connected에서 이미 로깅됨. 중복 없이 재전파.
    - 그 외 예외: message와 extra로 logger.exception을 기록한 후 재전파.

    반환하지 않음(NoReturn): 항상 예외를 raise하므로 호출 이후 코드는 도달 불가.
    이를 통해 각 public 메서드의 더미 return 문이 불필요해진다.
    """
    if isinstance(exc, RedisUnavailableError):
        raise exc  # 중복 로깅 방지
    logger.exception(message, extra=extra)
    raise exc


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

    def _parse_session_meta_for_list(
        self,
        user_id: str,
        session_id: str,
        raw: Any,
    ) -> Optional[Dict[str, Any]]:
        """mget 결과 1개를 파싱하고 보안 필터를 거쳐 dict를 반환한다.

        파싱 오류, 누락 키, 교차 유저 데이터 발견 시 None 반환.
        list_sessions의 루프 내 중첩을 제거하기 위한 헬퍼.
        """
        if not raw:
            return None
        try:
            meta = json.loads(raw)
            if not isinstance(meta, dict):
                raise ValueError("JSON is not a dict")
        except (JSONDecodeError, ValueError) as parse_err:
            logger.error(
                "Malformed session meta during list_sessions, skipping.",
                extra={"session_id_hash": _mask_id(session_id), "error": str(parse_err)},
            )
            return None

        # 보안: ZSET 오염으로 인한 교차 유저 데이터 유출 차단
        if meta.get("user_id") != user_id:
            logger.warning(
                "Cross-user session leakage detected and blocked.",
                extra={
                    "user_id_hash": _mask_id(user_id),
                    "session_id_hash": _mask_id(session_id),
                },
            )
            return None

        return meta

    async def _get_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """session_id에 해당하는 메타데이터 dict를 읽어 반환한다."""
        return await self._load_json_dict(
            self._session_meta_key(session_id),
            log_context="get_session_meta",
            id_hash=_mask_id(session_id),
        )

    async def _save_session_meta(self, session_id: str, meta: Dict[str, Any]) -> None:
        """메타데이터 dict를 Redis에 저장하고 TTL을 갱신한다."""
        key = self._session_meta_key(session_id)
        await redis_client.redis.set(key, json.dumps(meta, ensure_ascii=False))
        await redis_client.redis.expire(key, self.ttl)

    async def _build_session_meta(
        self,
        session_id: str,
        user_id: Optional[str],
        *,
        new_preview: Optional[str],
        now: datetime,
        force_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """메타 dict를 구성하여 반환한다.

        force_meta가 있으면 Redis 읽기를 건너뛰고 복사본을 기반으로 구성한다.
        force_meta가 없으면 기존 메타를 읽어 last_active_at·preview만 업데이트한다.
        """
        now_iso = now.isoformat()
        if force_meta is not None:
            meta = dict(force_meta)  # caller의 dict 직접 변경 방지
        else:
            meta = await self._get_session_meta(session_id) or {}

        effective_user_id = user_id or meta.get("user_id")
        meta.setdefault("session_id", session_id)
        meta.setdefault("created_at", now_iso)
        meta["last_active_at"] = now_iso
        if new_preview is not None:
            # Checklist (Null Safety): slicing 전에 대상 보장 및 result str 캐스팅
            meta["preview"] = str(new_preview)[:_PREVIEW_MAX_LEN]  # type: ignore[index]
        if effective_user_id:
            meta["user_id"] = effective_user_id

        return meta

    async def _update_session_index(
        self,
        session_id: str,
        user_id: Optional[str],
        now: datetime,
    ) -> None:
        """ZSET score를 갱신하여 최근 활성 순 정렬을 동기화한다."""
        if not user_id:
            return
        user_sessions_key = self._user_sessions_key(user_id)
        await redis_client.redis.zadd(user_sessions_key, {session_id: now.timestamp()})
        await redis_client.redis.expire(user_sessions_key, self.ttl)

    async def _touch_session(
        self,
        session_id: str,
        user_id: Optional[str],
        *,
        new_preview: Optional[str] = None,
        now: Optional[datetime] = None,
        force_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """세션 메타와 ZSET score를 단일 지점에서 갱신하는 오케스트레이터.

        _build_session_meta로 메타를 구성하고 _save_session_meta로 저장한 뒤,
        _update_session_index로 ZSET score를 갱신한다.
        """
        now = now or _now_utc()
        meta = await self._build_session_meta(
            session_id, user_id,
            new_preview=new_preview, now=now, force_meta=force_meta,
        )
        await self._save_session_meta(session_id, meta)
        await self._update_session_index(session_id, meta.get("user_id"), now)

    # ── 공개 API ───────────────────────────────────────────────

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

        try:
            await self._ensure_connected("register_session")

            now = _now_utc()
            existing_meta = await self._get_session_meta(session_id)
            created_at = (
                existing_meta.get("created_at", now.isoformat())
                if existing_meta
                else now.isoformat()
            )

            force_meta: Dict[str, Any] = {
                "session_id": session_id,
                "user_id": user_id,
                "name": name,
                "created_at": created_at,
                "preview": preview,
            }
            # ZSET 갱신 포함: _touch_session에 완전 위임 (SSOT)
            await self._touch_session(
                session_id, user_id, now=now, force_meta=force_meta
            )

        except Exception as e:
            _log_and_reraise_generic(
                "Failed to register session",
                {"session_id_hash": _mask_id(session_id), "error": str(e)},
                e,
            )

    async def list_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """사용자의 세션 목록을 최근 활성순으로 반환한다.

        mget을 사용해 N+1 Redis 호출을 ZSET 1회 + mget 1회로 최적화한다.
        보안: 메타의 user_id가 요청자와 일치하는 항목만 포함한다.

        Raises:
            ValueError: user_id 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not user_id:
            raise ValueError("user_id is required.")

        try:
            await self._ensure_connected("list_sessions")

            user_sessions_key = self._user_sessions_key(user_id)
            # str() 캐스팅: decode_responses 설정 변경에 방어적으로 str 보장
            raw_ids = await redis_client.redis.zrevrange(user_sessions_key, 0, -1)
            if not raw_ids:
                return []

            sids = [str(r) for r in raw_ids]
            meta_keys = [self._session_meta_key(sid) for sid in sids]

            # mget으로 N+1 → 2 Redis 라운드트립으로 최적화
            raws = await redis_client.redis.mget(*meta_keys)

            # _parse_session_meta_for_list가 파싱+보안 필터를 담당 (루프 평탄화)
            results: List[Dict[str, Any]] = []
            for sid, raw in zip(sids, raws):
                meta = self._parse_session_meta_for_list(user_id, sid, raw)
                if meta is not None:
                    results.append(meta)
            return results

        except Exception as e:
            _log_and_reraise_generic(
                "Failed to list sessions",
                {"user_id_hash": _mask_id(user_id), "error": str(e)},
                e,
            )

    async def rename_session(self, session_id: str, name: str) -> bool:
        """세션 이름을 수정한다. 세션이 없으면 False 반환.

        Raises:
            ValueError: 필수 입력 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not name:
            raise ValueError("session_id and name are required.")

        try:
            await self._ensure_connected("rename_session")

            meta = await self._get_session_meta(session_id)
            if meta is None:
                return False
            meta["name"] = name
            await self._save_session_meta(session_id, meta)
            return True

        except Exception as e:
            _log_and_reraise_generic(
                "Failed to rename session",
                {"session_id_hash": _mask_id(session_id), "error": str(e)},
                e,
            )

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        """메시지를 Redis 리스트에 추가하고 세션 메타와 ZSET score를 갱신한다.

        Raises:
            ValueError: session_id 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id is required to add messages to history.")

        try:
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
            # user_id=None → _build_session_meta가 메타에서 복원하여 ZSET도 업데이트
            await self._touch_session(
                session_id, user_id=None, new_preview=content, now=now
            )

        except Exception as e:
            _log_and_reraise_generic(
                "Failed to add message to history",
                {"session_id_hash": _mask_id(session_id), "error": str(e)},
                e,
            )

    async def get_history(self, session_id: str, limit: int = 20) -> List[ChatMessage]:
        """최근 대화 내역 조회.

        Raises:
            ValueError: session_id 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id is required to get chat history.")

        try:
            await self._ensure_connected("get_history")

            key = self._history_key(session_id)
            data = await redis_client.redis.lrange(key, -limit, -1)
            messages: List[ChatMessage] = []
            parse_errors: int = 0
            for item in data:
                msg_dict = self._parse_message(item)
                if msg_dict is None:
                    # Checklist (Wait): Linter가 parse_errors 타입을 인식 못 하는 경우를 위해 
                    # int 정체성 보장 (Pyre2 binding 이슈 대응)
                    parse_errors = int(parse_errors + 1)  # type: ignore[operator]
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

        except Exception as e:
            _log_and_reraise_generic(
                "Failed to get history",
                {"session_id_hash": _mask_id(session_id), "error": str(e)},
                e,
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

        try:
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

        except Exception as e:
            _log_and_reraise_generic(
                "Failed to clear history",
                {"session_id_hash": _mask_id(session_id), "error": str(e)},
                e,
            )


def get_chat_history_service() -> ChatHistoryService:
    return ChatHistoryService()

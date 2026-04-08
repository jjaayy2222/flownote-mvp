# backend/services/chat_history_service.py

import hashlib
import json
import logging
from json import JSONDecodeError
from typing import Any, Dict, List, NoReturn, Optional
from datetime import datetime, timezone
from backend.services.redis_pubsub import redis_client  # type: ignore[import]
from backend.api.models import ChatMessage  # type: ignore[import]
from backend.api.models.shared import FeedbackRating  # type: ignore[import]
from backend.utils import mask_pii_id  # type: ignore[import]

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Redis 키 프리픽스 상수
# ─────────────────────────────────────────────────────────────
_HISTORY_PREFIX = "chat:history:"
_SESSION_META_PREFIX = "chat:session:meta:"
_USER_SESSIONS_PREFIX = "chat:user:sessions:"
_FEEDBACK_PREFIX = "chat:feedback:"

# 외부 서비스(예: golden_dataset_service)에서 임포트 가능한 공개 상수.
# 단일 진실 공급원(SSOT): 피드백 키 프리픽스는 이 값에서만 변경하세요.
FEEDBACK_KEY_PREFIX: str = _FEEDBACK_PREFIX

# preview 최대 길이 (하드코딩 방지)
_PREVIEW_MAX_LEN = 80

# 피드백 통계 최대 반환 건수 (DRY: 엔드포인트와 서비스 계층 단일 진실 공급원)
MAX_FEEDBACK_STATS_LIMIT = 500


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
    logger.exception(f"[OBS] {message}", extra=extra)
    raise exc


def _decode_str(value: Any) -> str:
    """바이트일 경우 디코드하고, 그 외에는 문자열로 캐스팅하는 헬퍼"""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _process_feedback_entry(
    session_id: str,
    msg_id_raw: Any,
    meta_raw: Any,
    trends: Dict[str, Dict[str, int]],
) -> tuple[int, int, Optional[Dict[str, Any]]]:
    """단일 피드백 항목 파싱 및 가공을 담당하는 헬퍼"""
    msg_id = _decode_str(msg_id_raw)
    meta_str = _decode_str(meta_raw)

    try:
        meta = json.loads(meta_str)
    except (JSONDecodeError, ValueError, TypeError):
        return 0, 0, None

    raw_rating = meta.get("rating")
    # Frontend FeedbackRating Union 타입('up' | 'down' | 'none')과 일치시키기 위한 강제 캐스팅
    rating = raw_rating if raw_rating in ("up", "down") else "none"
    
    # timestamp가 int(epoch)이거나 str(ISO)일 수 있으므로 타입을 명시적으로 검증하여 정규화
    # 주의: bool은 int의 서브클래스이므로 명시적으로 제외 (True/False가 0/1 epoch으로 처리되는 것을 방지)
    raw_ts = meta.get("timestamp")
    if isinstance(raw_ts, (int, float, str)) and not isinstance(raw_ts, bool):
        ts = str(raw_ts).strip()
    else:
        # bool·비-스칼라 값(Dict/List) 또는 None인 경우 빈 문자열로 처리하여 예기치 못한 객체 문자화 방지
        ts = ""

    up_delta = 1 if rating == "up" else 0
    down_delta = 1 if rating == "down" else 0

    if ts and rating in ("up", "down"):
        date_str = ts[:10]
        day = trends.setdefault(date_str, {"up": 0, "down": 0})
        day[rating] += 1

    item = None
    text_content = meta.get("text")
    if text_content and (txt := str(text_content).strip()) and ts:
        item = {
            "session_id": session_id,
            "message_id": msg_id,
            "rating": rating,
            "text": txt,
            "timestamp": ts,
        }

    return up_delta, down_delta, item


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

    def _feedback_key(self, session_id: str) -> str:
        return f"{_FEEDBACK_PREFIX}{session_id}"

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
                extra={"session_id_hash": mask_pii_id(session_id), "error": str(parse_err)},
            )
            return None

        # 보안: ZSET 오염으로 인한 교차 유저 데이터 유출 차단
        if meta.get("user_id") != user_id:
            logger.warning(
                "Cross-user session leakage detected and blocked.",
                extra={
                    "user_id_hash": mask_pii_id(user_id),
                    "session_id_hash": mask_pii_id(session_id),
                },
            )
            return None

        return meta

    async def _get_session_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        """session_id에 해당하는 메타데이터 dict를 읽어 반환한다."""
        return await self._load_json_dict(
            self._session_meta_key(session_id),
            log_context="get_session_meta",
            id_hash=mask_pii_id(session_id),
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
                {"session_id_hash": mask_pii_id(session_id), "error": str(e)},
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
                {"user_id_hash": mask_pii_id(user_id), "error": str(e)},
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
                {"session_id_hash": mask_pii_id(session_id), "error": str(e)},
                e,
            )

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        message_id: Optional[str] = None,
    ) -> None:
        """메시지를 Redis 리스트에 추가하고 세션 메타와 ZSET score를 갱신한다.

        message_id가 제공되면 매시지 dict에 함께 저장하여, 평가 파이프라인(eval_service)이
        피드백 message_id와 정확히 매칭할 수 있도록 지원합니다.

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
            # message_id가 유효한 비공백 문자열인 경우에만 포함 (eval_service의 정확한 매칭에 사용됨)
            # 빈 문자열("")이나 공백만 있는 값도 저장하지 않아 eval 파이프라인의 오매칭을 방지합니다.
            if message_id and message_id.strip():
                message["message_id"] = message_id

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
                {"session_id_hash": mask_pii_id(session_id), "error": str(e)},
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
                        "session_id_hash": mask_pii_id(session_id),
                        "skipped_count": parse_errors,
                    },
                )
            return messages

        except Exception as e:
            _log_and_reraise_generic(
                "Failed to get history",
                {"session_id_hash": mask_pii_id(session_id), "error": str(e)},
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
                {"session_id_hash": mask_pii_id(session_id), "error": str(e)},
                e,
            )

    async def save_feedback(
        self,
        session_id: str,
        message_id: str,
        rating: FeedbackRating,
        feedback_text: Optional[str] = None,
    ) -> None:
        """AI 응답 사용자 피드백을 Redis Hash형태로 저장.

        Raises:
            ValueError: 필수 입력 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not message_id or not rating:
            raise ValueError("session_id, message_id, rating are required for feedback.")

        try:
            await self._ensure_connected("save_feedback")
            key = self._feedback_key(session_id)
            meta = {
                "rating": rating,
                "text": feedback_text,
                "timestamp": _now_utc().isoformat(),
            }
            await redis_client.redis.hset(key, message_id, json.dumps(meta, ensure_ascii=False))
            await redis_client.redis.expire(key, self.ttl)
        except Exception as e:
            _log_and_reraise_generic(
                "Failed to save feedback",
                {
                    "session_id_hash": mask_pii_id(session_id),
                    "message_id_hash": mask_pii_id(message_id),
                    "error": str(e),
                },
                e,
            )

    async def get_feedback_stats(self, limit_recent: int = 50) -> Dict[str, Any]:
        """AI 피드백 전체 통계를 집계하여 반환한다.
        
        Redis의 `scan`을 사용하여 모든 `chat:feedback:*` 키를 차단(Blocking) 없이 순회하고,
        일자별(Up/Down) 트렌드 및 최근 상세 피드백 내역(텍스트 포함)을 묶어서 반환한다.
        """
        import heapq
        
        # 내부 오작동 방지를 위한 상/하한선 (Service Layer clamping)
        limit_recent = max(1, min(limit_recent, MAX_FEEDBACK_STATS_LIMIT))
        
        try:
            await self._ensure_connected("get_feedback_stats")
            
            cursor = 0
            recent_heap: List[Any] = []
            tiebreaker = 0
            up_count = down_count = 0
            trends: Dict[str, Dict[str, int]] = {}

            # 1. 키 목록 수집 & 배치 단위 실시간 처리 (Streaming Aggregation 차용)
            while True:
                cursor, partial_keys = await redis_client.redis.scan(cursor, match=f"{_FEEDBACK_PREFIX}*", count=100)
                
                # 2. 배치별 즉시 처리
                for raw_key in partial_keys:
                    key_str = _decode_str(raw_key)
                    session_id = key_str.replace(_FEEDBACK_PREFIX, "")
                    
                    feedback_hash = await redis_client.redis.hgetall(key_str)
                    for msg_id_raw, meta_raw in feedback_hash.items():
                        up_delta, down_delta, item = _process_feedback_entry(
                            session_id, msg_id_raw, meta_raw, trends
                        )
                        up_count += up_delta
                        down_count += down_delta
                        
                        if item:
                            tiebreaker += 1
                            # Min-Heap 활용하여 O(1) 메모리 유지: timestamp가 가장 작은(오래된) 항목을 자동 pop
                            heapq.heappush(recent_heap, (item["timestamp"], tiebreaker, item))
                            if len(recent_heap) > limit_recent:
                                heapq.heappop(recent_heap)
                            
                # 안전하게 int로 캐스팅하여 종료 조건 체크
                if int(cursor) == 0:
                    break

            # 3. YYYY-MM-DD 정렬
            sorted_trends = [
                {"date": d, "up": trends[d]["up"], "down": trends[d]["down"]}
                for d in sorted(trends.keys())
            ]
            
            # 4. Heap에서 아이템 추출 후 최신순 역렬
            recent_feedbacks = sorted(
                [val for _, _, val in recent_heap],
                key=lambda x: x.get("timestamp", ""),
                reverse=True,
            )
            
            return {
                "total_up": up_count,
                "total_down": down_count,
                "trends": sorted_trends,
                "recent_feedbacks": recent_feedbacks
            }

        except Exception as e:
            _log_and_reraise_generic(
                "Failed to get feedback stats",
                {"error": str(e)},
                e,
            )

    async def get_session_feedback(self, session_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """특정 세션의 최근 피드백 이력을 조회합니다.
        
        Raises:
            ValueError: session_id 누락.
            RedisUnavailableError: Redis 연결 불가.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id is required to get session feedback.")

        try:
            await self._ensure_connected("get_session_feedback")
            key = self._feedback_key(session_id)
            feedback_hash = await redis_client.redis.hgetall(key)
            
            def _parse_timestamp(ts: Any) -> float:
                if isinstance(ts, (int, float)) and not isinstance(ts, bool):
                    return float(ts)
                if isinstance(ts, str):
                    ts_str = ts.strip()
                    try:
                        # ISO 8601 parsing fallback
                        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        try:
                            # Numeric string fallback
                            return float(ts_str)
                        except ValueError:
                            pass
                return 0.0
            
            feedbacks: List[Dict[str, Any]] = []
            for msg_id_raw, meta_raw in feedback_hash.items():
                msg_id = _decode_str(msg_id_raw)
                meta_str = _decode_str(meta_raw)
                try:
                    meta = json.loads(meta_str)
                    if isinstance(meta, dict):
                        raw_ts = meta.get("timestamp")
                        if isinstance(raw_ts, (int, float, str)) and not isinstance(raw_ts, bool):
                            ts_str = str(raw_ts).strip()
                        else:
                            ts_str = ""
                            
                        feedbacks.append({
                            "message_id": msg_id,
                            "rating": str(meta.get("rating", "none")),
                            "text": str(meta.get("text")) if meta.get("text") else None,
                            "timestamp": ts_str,
                            "_sort_key": _parse_timestamp(raw_ts)
                        })
                except (JSONDecodeError, ValueError, TypeError):
                    continue
                    
            # 최신순 정렬 (숫자형 우선, 내림차순) 후 제한된 개수만 잘라서 반환 (_sort_key 제거)
            feedbacks.sort(key=lambda x: x["_sort_key"], reverse=True)
            result = []
            for f in feedbacks[:limit]:
                del f["_sort_key"]
                result.append(f)
                
            return result

        except Exception as e:
            _log_and_reraise_generic(
                "Failed to get session feedback",
                {"session_id_hash": mask_pii_id(session_id), "error": str(e)},
                e,
            )


def get_chat_history_service() -> ChatHistoryService:
    return ChatHistoryService()


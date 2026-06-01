# backend/api/endpoints/chat_stream.py

"""
SSE 스트리밍 채팅 엔드포인트 (Phase 3 — 2단계: Integration)
=============================================================

역할:
  ChatQueryRequest를 수신하여 LangGraph 에이전트(stream_agent_response)를
  SSE 형식으로 클라이언트에 직접 전달한다.

설계 결정 (1차 개선):
  - 스캐폴딩 단계에서 asyncio.Queue + 프로듀서/컨슈머 이중 구조는 불필요한 복잡성을 추가하며,
    다음의 실제 버그를 내포하고 있었습니다:
      1. finally 블록의 `await queue.put(None)` — 큐 포화 + 컨슈머 종료 시 데드락 위험
      2. disconnect 체크가 각 청크 처리 이후에만 실행 — 느린 teardown
      3. 주석의 "drop oldest" 설명과 실제 blocking put() 동작 불일치
  - 이를 해결하기 위해 단일 루프 + 내부 `_chunk_stream()` 제너레이터 패턴으로 단순화.
  - `asyncio.timeout()` 컨텍스트 매니저로 전체 스트림에 명확한 타임아웃 범위 적용.
  - 3단계(실제 에이전트 연결) 시 `_chunk_stream()` 본문만 교체하면 되도록 인터페이스 유지.

하드코딩 금지:
  - 모든 설정값은 StreamingConfig.load()를 통해 외부 환경 변수에서 로드
  - SSE 이벤트 이름은 클라이언트 API 계약이므로 모듈 수준 상수로 관리
"""

import asyncio
import logging
import time
import uuid
from itertools import islice
from typing import Any, AsyncGenerator

import anyio
import anyio.to_thread
from cachetools import TTLCache  # type: ignore[import, import-untyped]
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.agent.streaming import stream_agent_response  # noqa: F401 (3단계 연동 예정)
from backend.api.models import ChatQueryRequest
from backend.core.config.streaming import StreamingConfig
from backend.schemas.streaming import DoneChunk, ErrorChunk, StreamChunk, TokenChunk
from backend.utils import get_chat_log_extra
from backend.core.config_validator import GraphEngineConfig, PersonalizedRAGConfig
from backend.graph import NetworkXGraphRepository
from backend.services.personalized_index_service import compute_hashed_user_id
from backend.core.aws_client_wrapper import fetch_global_pepper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat-stream"])

# ─────────────────────────────────────────────────────────────────────────────
# 모듈 로드 시점 설정 로드 (환경 변수 반영 + Clamp 보장)
# ─────────────────────────────────────────────────────────────────────────────
_cfg = StreamingConfig.load()
_graph_cfg = GraphEngineConfig.from_env()
_rag_cfg = PersonalizedRAGConfig.from_env()

# ─────────────────────────────────────────────────────────────────────────────
# SSE 동시성 모니터링 상태 (Per-worker)
# ─────────────────────────────────────────────────────────────────────────────
_active_sse_sessions: int = 0
_sse_sessions_lock = asyncio.Lock()

async def sse_session_tracker() -> AsyncGenerator[int, None]:
    """
    FastAPI Depends: 워커 인스턴스(Per-worker) 내부 SSE 세션 수를 추적합니다.
    """
    global _active_sse_sessions
    async with _sse_sessions_lock:
        _active_sse_sessions += 1
    
    try:
        yield _active_sse_sessions
    finally:
        async with _sse_sessions_lock:
            _active_sse_sessions -= 1

# ─────────────────────────────────────────────────────────────────────────────
# 전역 의존성 캐싱 (Per-worker)
# ─────────────────────────────────────────────────────────────────────────────
_pepper_cache: TTLCache = TTLCache(maxsize=1, ttl=300)  # 5분 단위 갱신
_pepper_lock = asyncio.Lock()

async def get_cached_global_pepper() -> str:
    """KMS 지연시간 감소를 위한 global_pepper 메모리 캐싱"""
    # Fast path: lock-free atomic read (TOCTOU 방지)
    cached_pepper = _pepper_cache.get("pepper")
    if cached_pepper is not None:
        return cached_pepper

    # Slow path: 잠금 기반 double-checked 패턴으로 KMS 호출
    async with _pepper_lock:
        cached_pepper = _pepper_cache.get("pepper")
        if cached_pepper is not None:
            return cached_pepper
        pepper = await fetch_global_pepper()
        _pepper_cache["pepper"] = pepper
        return pepper

# SSE 이벤트 이름 상수 (클라이언트 API 계약 — 하드코딩 방지)
# 프론트엔드와 동기화된 표준 이벤트 이름이므로, 변경 시 이 상수만 수정하면 됩니다.
_SSE_EVENT_MESSAGE: str = "message"
_SSE_EVENT_ERROR: str = "error"
_SSE_EVENT_DONE: str = "done"

_LOG_TAG: str = "[STREAM]"

# 클라이언트에 전달할 일반화된 에러 메시지 (하드코딩 방지)
# 내부 구현 세부사항(스택 트레이스 등) 클라이언트 노출 방지 — Information Disclosure 예방
_ERROR_MSG_INTERNAL: str = "Internal server error occurred during streaming."
_ERROR_MSG_TIMEOUT: str = "Streaming session timed out. Please retry."
_ERROR_MSG_SCHEMA: str = "Data format mismatch detected. Please contact support."

# _safe_repr 재귀 최대 깊이 (하드코딩 방지 — 비정상 중첩 객체로 인한 Stack Overflow 방어)
_SAFE_REPR_MAX_DEPTH: int = 3
# _safe_repr dict 최대 키 출력 수 (하드코딩 방지 — 대형 dict로 인한 로그 크기 팽창 방어)
_SAFE_REPR_MAX_KEYS: int = 10


def _safe_repr(obj: Any, _depth: int = 0) -> str:
    """
    민감 데이터(PII)의 로깅 노출 위험 없이 스키마 불일치 디버깅을 돕기 위해
    객체의 구조(필드/키/타입/길이) 정보만 안전하게 추출하여 반환합니다.

    Args:
        obj: 안전하게 표현할 대상 객체
        _depth: 내부 재귀 깊이 추적용 (외부에서 직접 전달하지 않음)

    [설계 결정 - 재귀 깊이 제한]:
    비정상적으로 깊은 중첩 객체(list of list of list...)가 인입될 경우
    Stack Overflow 또는 로그 크기 무제한 팽창을 방지하기 위해
    _SAFE_REPR_MAX_DEPTH 상수로 최대 깊이를 제한합니다.
    """
    if obj is None:
        return "None"

    # 재귀 깊이 초과 시 즉시 타입 정보만 반환 (안전망)
    if _depth >= _SAFE_REPR_MAX_DEPTH:
        return f"<max_depth_reached: {type(obj).__name__}>"

    try:
        if isinstance(obj, BaseModel):
            # model_fields는 클래스 속성이므로 인스턴스 접근 대신 타입으로 조회 (Pydantic V3 호환)
            fields = list(type(obj).model_fields.keys())
            return f"{obj.__class__.__name__}(fields={fields})"
        elif isinstance(obj, dict):
            # [설계 결정] islice를 사용하여 전체 키를 list로 구체화하지 않고 최대 _SAFE_REPR_MAX_KEYS 개만 순회
            # (실제 연산 복잡도: O(min(total_keys, _SAFE_REPR_MAX_KEYS)) -> 최대 _SAFE_REPR_MAX_KEYS 개만 순회)
            # len(obj)는 dict의 O(1) 연산이므로 전체 순회 없이 총 키 수 확인 가능
            total_keys = len(obj)
            sampled_keys = list(islice(obj.keys(), _SAFE_REPR_MAX_KEYS))
            suffix = ", ..." if total_keys > _SAFE_REPR_MAX_KEYS else ""
            return f"dict(total_keys={total_keys}, sampled_keys={sampled_keys}{suffix})"
        elif isinstance(obj, list):
            # 항목 3개까지만 표시하며, 각 항목도 깊이를 증가시켜 재귀 제한 적용
            elem_reprs = [_safe_repr(item, _depth + 1) for item in obj[:3]]
            if len(obj) > 3:
                elem_reprs.append("...")
            return f"list(size={len(obj)}, items={elem_reprs})"
        elif isinstance(obj, str):
            # 문자열은 길이 정보만 제공하여 PII 노출 방지
            return f"str(length={len(obj)})"
        elif isinstance(obj, (int, float, bool)):
            return repr(obj)
        else:
            return f"{obj.__class__.__name__}(type={type(obj)})"
    except Exception as e:
        return f"<repr_error: {type(e).__name__}>"


@router.post(
    "/stream",
    summary="RAG 채팅 결과 스트리밍 (SSE)",
    description=(
        "사용자의 질문을 기반으로 RAG 파이프라인을 거쳐 응답을 "
        "Server-Sent Events(SSE) 형식으로 반환합니다."
    ),
)
async def stream_chat_endpoint(
    request: Request,
    body: ChatQueryRequest,
    current_sse_count: int = Depends(sse_session_tracker),
) -> EventSourceResponse:
    """
    SSE 기반 스트리밍 엔드포인트 (2단계: 어댑터 연결).

    흐름:
      1. 내부 _chunk_stream() 제너레이터에서 StreamChunk를 순차 발행
      2. asyncio.timeout()으로 전체 스트림에 타임아웃 적용
      3. 각 청크 처리 후 클라이언트 disconnect 감지 → 즉시 종료
      4. TTFT / 총 스트리밍 시간 / 청크 수를 구조화 로그로 기록
    """
    # PII 마스킹 적용 구조화 로그
    logger.info(
        "%s Request received.",
        _LOG_TAG,
        extra=get_chat_log_extra(body),
    )

    # ── 마이그레이션 트리거 모니터링 (3단계) ──────────────────────────────────────────
    try:
        # [설계결정] DB 연동 전까지 user_id를 이용해 임시 salt 구성
        per_user_salt = f"mock_salt_{body.user_id}"
        global_pepper = await get_cached_global_pepper()
        
        hashed_uid = compute_hashed_user_id(body.user_id, per_user_salt, global_pepper)
        
        # [설계결정] node_count는 디스크 I/O를 유발하므로 이벤트 루프 블로킹을 방지하고, 
        # 스레드 안전성(Thread-safety) 확보 및 상태 공유 차단을 위해 스레드 내부에서 리포지토리 독립 인스턴스를 생성
        def _get_node_count() -> int:
            local_repo = NetworkXGraphRepository(storage_base_path=_rag_cfg.storage_base_path)
            try:
                local_repo.load(hashed_uid)
                return local_repo.node_count(hashed_uid)
            finally:
                # 명시적 메모리 해제를 통해 인스턴스 소멸 전 GC 부담 경감
                local_repo.clear(hashed_uid)
            
        current_node_count = await anyio.to_thread.run_sync(_get_node_count)
    except Exception as exc:
        logger.warning(
            "%s[MIGRATION] Failed to fetch node count for trigger: %s",
            _LOG_TAG,
            exc,
        )
        current_node_count = 0

    if (
        current_node_count > _graph_cfg.migration_node_threshold
        or current_sse_count > _graph_cfg.migration_concurrency_threshold
    ):
        logger.warning(
            "%s[MIGRATION_TRIGGER] Neo4j migration recommended. "
            "node_count=%d (threshold=%d), sse_sessions=%d (threshold=%d)",
            _LOG_TAG,
            current_node_count,
            _graph_cfg.migration_node_threshold,
            current_sse_count,
            _graph_cfg.migration_concurrency_threshold,
        )

    async def event_generator() -> AsyncGenerator[dict, None]:
        # ── 설정값 로컬 바인딩 ────────────────────────────────────────────────
        timeout_secs: int = _cfg.timeout_secs

        # ── 관측성 메트릭 초기화 ─────────────────────────────────────────────
        request_start: float = time.monotonic()
        first_token_time: float | None = None
        chunk_count: int = 0

        # ── 내부 청크 제너레이터 ─────────────────────────────────────────────
        async def _chunk_stream() -> AsyncGenerator[StreamChunk, None]:
            """
            LangGraph 어댑터 인터페이스를 모델링하는 내부 청크 제너레이터.

            NOTE (2단계 스캐폴딩):
              현재는 더미 청크를 발행합니다.
              3단계(실제 에이전트 연결)에서 이 본문만 교체 예정:

              async for chunk in stream_agent_response(graph, inputs, config):
                  yield chunk
            """
            try:
                from backend.services.chat_service import get_chat_service
                from backend.agent.streaming import stream_agent_response
                from langchain_core.runnables import RunnableConfig  # type: ignore[import]

                chat_service = get_chat_service()

                # 기존 /api/chat 엔드포인트와 공통 로직 리팩터링 (재사용)
                initial_state, agent_graph = await chat_service.build_agent_state_and_graph(
                    query=body.query,
                    user_id=body.user_id,
                    session_id=body.session_id,
                )

                # downstream 컴포넌트 오류 방지를 위한 식별자 정규화
                effective_session_id = body.session_id if body.session_id and body.session_id.strip() else f"temp_{uuid.uuid4().hex}"
                config = RunnableConfig(configurable={"thread_id": effective_session_id})

                # 실제 LangGraph 스트리밍 어댑터 호출
                async for chunk in stream_agent_response(agent_graph, initial_state, config):
                    yield chunk

            except Exception as exc:  # noqa: BLE001
                # 청크 발행 중 예상치 못한 예외
                # 서버 로그에는 상세 정보 기록, 클라이언트에는 일반화된 메시지만 전달
                # str(exc)를 클라이언트에 직접 노출하면 내부 경로·데이터가 유출될 수 있음
                logger.error(
                    "%s[ERROR] _chunk_stream raised unexpected error",
                    _LOG_TAG,
                    exc_info=True,
                )
                yield ErrorChunk(
                    code="PRODUCER_ERROR",
                    message=_ERROR_MSG_INTERNAL,  # 내부 오류 메시지 사용
                )

        # ── 메인 컨슈머 루프 ─────────────────────────────────────────────────
        stream_gen: AsyncGenerator[StreamChunk, None] | None = None
        try:
            stream_gen = _chunk_stream()  # 제너레이터 객체 생성
            # asyncio.timeout: 전체 스트림에 명확한 타임아웃 범위 지정 (Python 3.11+)
            async with asyncio.timeout(timeout_secs):
                async for chunk in stream_gen:
                    # ── TokenChunk 처리 ───────────────────────────────────
                    if isinstance(chunk, TokenChunk):
                        if first_token_time is None:
                            first_token_time = time.monotonic()
                            ttft_ms = (first_token_time - request_start) * 1000
                            logger.info(
                                "%s[TTFT] Time to first token: %.1fms",
                                _LOG_TAG,
                                ttft_ms,
                            )
                        chunk_count += 1
                        yield {
                            "event": _SSE_EVENT_MESSAGE,
                            "data": chunk.model_dump_json(),
                        }

                    # ── DoneChunk 처리 ────────────────────────────────────
                    elif isinstance(chunk, DoneChunk):
                        total_secs = time.monotonic() - request_start
                        logger.info(
                            "%s Streaming completed. chunks=%d, total_time=%.2fs",
                            _LOG_TAG,
                            chunk_count,
                            total_secs,
                        )
                        yield {
                            "event": _SSE_EVENT_DONE,
                            "data": chunk.model_dump_json(),
                        }
                        break

                    # ── ErrorChunk 처리 ───────────────────────────────────
                    elif isinstance(chunk, ErrorChunk):
                        logger.error(
                            "%s[ERROR] ErrorChunk received: code=%s",
                            _LOG_TAG,
                            chunk.code,
                        )
                        yield {
                            "event": _SSE_EVENT_ERROR,
                            "data": chunk.model_dump_json(),
                        }
                        break

                    # ── 알 수 없는 청크 타입 처리 (안전망) ────────────────────
                    # TokenChunk / DoneChunk / ErrorChunk 외의 타입이 발행되면
                    # 조용히 드랍되지 않도록 경고 로그 + 에러 이벤트로 가시화합니다.
                    #
                    # [설계 결정 - 즉시 중단(break)의 의도된 거동 및 안전성 검증]:
                    # 1. 스트림 무결성 보장: 스키마 불일치(SCHEMA MISMATCH)가 한 번 발생하면, 이후의 후속 데이터들 역시 비정상적이거나
                    #    클라이언트(프론트엔드)에서 파싱 및 렌더링에 실패하여 애플리케이션 오동작을 초래할 수 있으므로 스트림을 즉시 중단합니다.
                    # 2. 리소스 누수 방지: 즉시 break하여 루프를 탈출하면, finally 블록으로 넘어가 `stream_gen.aclose()`가 안전하게 실행되며,
                    #    이로 인해 generator가 즉시 회수되어 어떠한 리소스 누수도 발생하지 않습니다.
                    # 3. 버퍼 비워짐 영향 없음: 현재 구조는 인메모리 큐를 거치지 않고 제너레이터로부터 청크를 직접 온디맨드식으로
                    #    비동기 순회하므로, 스킵된 '버퍼링된 잔여 청크'가 존재하지 않아 클라이언트에 혼선을 유발하지 않습니다.
                    else:
                        logger.warning(
                            "%s[SCHEMA] Unknown chunk type received: %s. "
                            "safe_payload=%s. Possible schema mismatch.",
                            _LOG_TAG,
                            type(chunk).__name__,
                            _safe_repr(chunk),  # PII 유출 위험이 전혀 없는 구조 정보와 비민감 메타데이터 로깅 (안전성 우선 원칙)
                        )
                        yield {
                            "event": _SSE_EVENT_ERROR,
                            "data": ErrorChunk(
                                code="UNKNOWN_CHUNK",
                                message=_ERROR_MSG_SCHEMA,  # 스키마 불일치용 일반화 에러 메시지
                            ).model_dump_json(),
                        }
                        break

                    # ── 클라이언트 disconnect 감지 (각 청크 처리 후 즉시 확인) ──
                    if await request.is_disconnected():
                        logger.info("%s Client disconnected. Stopping stream.", _LOG_TAG)
                        break

        except asyncio.TimeoutError:
            # asyncio.timeout() 초과 시 asyncio.TimeoutError 발생 (Python 3.11+)
            # 명시적으로 asyncio.TimeoutError를 잡아 무관한 TimeoutError와 구분
            logger.warning(
                "%s Session timed out after %ds.",
                _LOG_TAG,
                timeout_secs,
            )
            yield {
                "event": _SSE_EVENT_ERROR,
                "data": ErrorChunk(
                    code="STREAM_TIMEOUT",
                    message=_ERROR_MSG_TIMEOUT,  # 타임아웃 전용 메시지
                ).model_dump_json(),
            }

        except asyncio.CancelledError:
            logger.info("%s Event generator cancelled.", _LOG_TAG)
            raise

        except Exception as exc:  # noqa: BLE001
            # 메인 루프 예외 처리 (로그 기록 후 에러 청크 발행)
            logger.error(
                "%s[FATAL] Event generator encountered unexpected error",
                _LOG_TAG,
                exc_info=True,
            )
            yield {
                "event": _SSE_EVENT_ERROR,
                "data": ErrorChunk(
                    code="FATAL_ERROR",
                    message=_ERROR_MSG_INTERNAL,
                ).model_dump_json(),
            }

        finally:
            # 리소스 정리 강화: 제너레이터를 안전하게 종료 (리뷰 반영)
            if stream_gen is not None:
                try:
                    await stream_gen.aclose()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "%s[CLEANUP] Failed to close stream generator gracefully.",
                        _LOG_TAG,
                        exc_info=True,
                    )
            
            total_elapsed = time.monotonic() - request_start
            logger.info(
                "%s Session closed. total_elapsed=%.2fs, chunks_sent=%d",
                _LOG_TAG,
                total_elapsed,
                chunk_count,
            )

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

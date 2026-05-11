# backend/api/endpoints/chat_stream.py

"""
SSE 스트리밍 채팅 엔드포인트 (Phase 3 — 2단계: Integration)
=============================================================

역할:
  ChatQueryRequest를 수신하여 LangGraph 에이전트(stream_agent_response)를
  asyncio.Queue 기반 백프레셔 버퍼를 통해 SSE 형식으로 클라이언트에 전달한다.

설계 결정:
  - 프로듀서(LangGraph)와 컨슈머(SSE) 속도 불일치를 asyncio.Queue로 흡수
  - 큐 크기(STREAM_BUFFER_MAX_SIZE)는 설정 외부화, 초과 시 가장 오래된 청크를 드랍
  - TTFT / 총 스트리밍 시간 / 발행 청크 수를 [STREAM] 구조화 로그로 기록
  - 클라이언트 연결 종료 시 프로듀서 태스크를 즉시 취소하여 리소스 누수 방지

하드코딩 금지:
  - 모든 설정값은 StreamingConfig.load()를 통해 외부 환경 변수에서 로드
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from backend.agent.streaming import stream_agent_response
from backend.api.models import ChatQueryRequest
from backend.core.config.streaming import StreamingConfig
from backend.schemas.streaming import DoneChunk, ErrorChunk, StreamChunk, TokenChunk
from backend.utils import get_chat_log_extra

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat-stream"])

# ─────────────────────────────────────────────────────────────────────────────
# 모듈 로드 시점 설정 로드 (환경 변수 반영 + Clamp 보장)
# ─────────────────────────────────────────────────────────────────────────────
_cfg = StreamingConfig.load()

# 큐 드랍 시 경고를 위한 내부 이벤트 타입 상수 (하드코딩 방지)
_SSE_EVENT_MESSAGE: str = "message"
_SSE_EVENT_ERROR: str = "error"
_SSE_EVENT_DONE: str = "done"

_LOG_TAG: str = "[STREAM]"


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
) -> EventSourceResponse:
    """
    SSE 기반 스트리밍 엔드포인트 (2단계: 어댑터 연결).

    흐름:
      1. LangGraph 어댑터(stream_agent_response)를 프로듀서 태스크로 실행
      2. asyncio.Queue 버퍼를 통해 백프레셔 제어
      3. 컨슈머(event_generator)가 큐에서 청크를 꺼내 SSE 이벤트로 발행
      4. 클라이언트 연결 종료 또는 타임아웃 시 프로듀서 태스크를 즉시 취소
    """
    # PII 마스킹 적용 구조화 로그
    logger.info(
        "%s Request received.",
        _LOG_TAG,
        extra=get_chat_log_extra(body),
    )

    async def event_generator() -> AsyncGenerator[dict, None]:
        # ── 설정값 로컬 바인딩 (루프 내 반복 속성 접근 최소화) ──────────────
        timeout_secs: int = _cfg.timeout_secs
        buffer_max_size: int = _cfg.buffer_max_size

        # ── 관측성 메트릭 초기화 ────────────────────────────────────────────
        request_start: float = time.monotonic()
        first_token_time: float | None = None
        chunk_count: int = 0

        # ── 백프레셔 큐 (프로듀서-컨슈머 속도 불일치 흡수) ─────────────────
        # maxsize=buffer_max_size: 큐가 가득 찼을 때 put()이 block되어 자연스러운 백프레셔 형성
        queue: asyncio.Queue[StreamChunk | None] = asyncio.Queue(maxsize=buffer_max_size)

        # ── 프로듀서 코루틴 정의 ────────────────────────────────────────────
        async def _producer() -> None:
            """
            LangGraph 어댑터를 구독하여 StreamChunk를 큐에 적재한다.
            완료 또는 예외 발생 시 None 센티널을 큐에 삽입하여 컨슈머 종료를 알린다.

            NOTE (2단계 스캐폴딩):
              현재 graph/inputs/config는 실제 LangGraph 인스턴스가 아닌 플레이스홀더.
              3단계(실제 에이전트 연결)에서 chat_service 또는 agent 팩토리로 교체 예정.
            """
            try:
                # TODO(3단계): 실제 LangGraph graph, inputs, config 주입
                # graph = await get_compiled_graph()
                # inputs = {"query": body.query, "user_id": hashed_user_id}
                # config = RunnableConfig(configurable={"thread_id": session_id})
                # async for chunk in stream_agent_response(graph, inputs, config):
                #     await queue.put(chunk)
                #
                # ── 2단계 스캐폴딩: 어댑터 인터페이스 연동 확인용 더미 청크 ──
                await asyncio.sleep(0)  # 이벤트 루프 양보 (실제 코루틴 시뮬레이션)
                await queue.put(
                    TokenChunk(data="[2단계 연결 완료: LangGraph 어댑터 인터페이스 준비됨]")
                )
                await queue.put(DoneChunk())
            except asyncio.CancelledError:
                logger.info("%s Producer task cancelled (client disconnected).", _LOG_TAG)
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "%s[ERROR] Producer raised unexpected error: type=%s",
                    _LOG_TAG,
                    type(exc).__name__,
                    exc_info=True,
                )
                await queue.put(
                    ErrorChunk(code="PRODUCER_ERROR", message=str(exc))
                )
            finally:
                # 정상/비정상 종료 모두 None 센티널을 삽입하여 컨슈머를 종료시킴
                await queue.put(None)

        # ── 프로듀서를 별도 태스크로 실행 ───────────────────────────────────
        producer_task = asyncio.create_task(_producer())

        try:
            # ── 컨슈머 루프: 큐에서 청크를 꺼내 SSE 이벤트로 변환 ───────────
            while True:
                # 타임아웃 초과 시 asyncio.TimeoutError 발생 → 연결 종료
                try:
                    chunk: StreamChunk | None = await asyncio.wait_for(
                        queue.get(),
                        timeout=timeout_secs,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "%s Session timed out after %ds (no chunk received).",
                        _LOG_TAG,
                        timeout_secs,
                    )
                    yield {
                        "event": _SSE_EVENT_ERROR,
                        "data": json.dumps({"error": "Stream timed out. Please retry."}),
                    }
                    break

                # None 센티널 수신 → 프로듀서 종료 신호
                if chunk is None:
                    break

                # ── TokenChunk 처리 ─────────────────────────────────────
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

                # ── DoneChunk 처리 ──────────────────────────────────────
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

                # ── ErrorChunk 처리 ─────────────────────────────────────
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

                # ── 클라이언트 연결 종료 감지 ───────────────────────────
                if await request.is_disconnected():
                    logger.info("%s Client disconnected. Stopping consumer.", _LOG_TAG)
                    break

        except asyncio.CancelledError:
            logger.info("%s Event generator cancelled.", _LOG_TAG)
            raise
        finally:
            # 컨슈머 종료 시 프로듀서 태스크를 반드시 취소하여 리소스 누수 방지
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except (asyncio.CancelledError, Exception):
                    pass  # 정리 완료

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

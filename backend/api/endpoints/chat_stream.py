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
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from backend.agent.streaming import stream_agent_response  # noqa: F401 (3단계 연동 예정)
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
                # TODO(3단계): 실제 LangGraph graph, inputs, config 주입
                # graph = await get_compiled_graph()
                # inputs = {"query": body.query, "user_id": hashed_user_id}
                # config = RunnableConfig(configurable={"thread_id": session_id})
                # async for chunk in stream_agent_response(graph, inputs, config):
                #     yield chunk

                # 2단계 스캐폴딩: 어댑터 인터페이스 검증용 더미 청크
                await asyncio.sleep(0)  # 이벤트 루프 양보 (비동기 코루틴 시뮬레이션)
                yield TokenChunk(data="[2단계 연결 완료: LangGraph 어댑터 인터페이스 준비됨]")
                yield DoneChunk()

            except Exception as exc:  # noqa: BLE001
                # 청크 발행 중 예상치 못한 예외
                # 서버 로그에는 상세 정보 기록, 클라이언트에는 일반화된 메시지만 전달
                # str(exc)를 클라이언트에 직접 노출하면 내부 경로·데이터가 유출될 수 있음
                logger.error(
                    "%s[ERROR] _chunk_stream raised unexpected error: type=%s, detail=%s",
                    _LOG_TAG,
                    type(exc).__name__,
                    str(exc),  # 상세 정보는 서버 로그에만 기록
                    exc_info=True,
                )
                yield ErrorChunk(
                    code="PRODUCER_ERROR",
                    message=_ERROR_MSG_INTERNAL,  # 내부 오류 메시지 사용
                )

        # ── 메인 컨슈머 루프 ─────────────────────────────────────────────────
        stream_gen = _chunk_stream()  # 제너레이터 객체 생성
        try:
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
                    # 조용히 드랍되지 않도록 경고 로그 + 에러 이벤트로 가시화.
                    # 스키마 불일치 발생 시 스트림 무결성을 위해 즉시 중단(break)합니다.
                    else:
                        logger.warning(
                            "%s[SCHEMA] Unknown chunk type received: %s. "
                            "payload=%r. Possible schema mismatch.",
                            _LOG_TAG,
                            type(chunk).__name__,
                            chunk,
                        )
                        yield {
                            "event": _SSE_EVENT_ERROR,
                            "data": ErrorChunk(
                                code="UNKNOWN_CHUNK",
                                message=_ERROR_MSG_SCHEMA,  # 스캐마 불일치 메시지
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
                "%s[FATAL] Event generator encountered unexpected error: %s",
                _LOG_TAG,
                str(exc),
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
            # 리소스 정리 강화: 제너레이터를 명시적으로 종료하여 
            # 프로듀서 측의 백그라운드 태스크나 리소스 누수를 방지 (리뷰 반영)
            await stream_gen.aclose()
            
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

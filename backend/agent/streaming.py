# backend/agent/streaming.py

"""
LangGraph 스트리밍 어댑터 (Phase 3 — Realtime Streaming)
=========================================================

역할:
  LangGraph Native API(`astream_events`)를 구독하여 모델이 생성하는 토큰을
  `StreamChunk` 스키마로 변환·발행하는 비동기 제너레이터 레이어.

설계 결정 — LangGraph Native API 채택 이유:
  - LangChain 레거시 콜백 핸들러 방식은 상태 머신 로직과 사이드 이펙트가
    결합되어 테스트와 유지보수가 어렵습니다.
  - LangGraph Native `astream_events` 방식은 이벤트 스트림을 선언적으로
    필터링하며, 그래프 상태 머신과의 결합도가 낮아 이 프로젝트의 표준으로 채택합니다.

하드코딩 금지:
  - LangGraph 스트리밍 API 버전은 `STREAMING_DEFAULT_STREAM_VERSION` 상수를 사용합니다.
  - 이벤트 타입 문자열은 모듈 수준 상수로 중앙 정의합니다.

보안:
  - 예외 메시지는 PII가 포함될 수 있으므로 `ErrorChunk.message`의 Pydantic
    `@field_validator`가 자동으로 `mask_pii_id()`를 적용합니다.
  - 스트리밍 세션 식별자는 로그에 원문 노출 없이 hashed_user_id만 사용합니다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from backend.core.config.streaming import STREAMING_DEFAULT_STREAM_VERSION
from backend.schemas.streaming import (
    DoneChunk,
    ErrorChunk,
    StreamChunk,
    StreamChunkType,
    TokenChunk,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LangGraph 이벤트 타입 상수 (문자열 하드코딩 방지)
# LangGraph astream_events v2 기준 이벤트 이름
# ─────────────────────────────────────────────────────────────────────────────

_LANGGRAPH_EVENT_ON_CHAT_MODEL_STREAM: str = "on_chat_model_stream"
_LANGGRAPH_EVENT_ON_LLM_STREAM: str = "on_llm_stream"

# 토큰 청크 데이터 접근 키
_CHUNK_KEY: str = "chunk"
_CONTENT_KEY: str = "content"

# 에러 코드 상수 (하드코딩 방지)
_ERROR_CODE_STREAM_ERROR: str = "STREAM_ERROR"
_ERROR_CODE_CLIENT_DISCONNECT: str = "CLIENT_DISCONNECT"


# ─────────────────────────────────────────────────────────────────────────────
# 메인 스트리밍 어댑터
# ─────────────────────────────────────────────────────────────────────────────


async def stream_agent_response(
    graph: CompiledStateGraph,
    inputs: dict[str, Any],
    config: dict[str, Any],
    *,
    stream_version: str = STREAMING_DEFAULT_STREAM_VERSION,
) -> AsyncIterator[StreamChunk]:
    """
    LangGraph 그래프를 실행하고 모델이 생성하는 토큰을 `StreamChunk`로 발행한다.

    이 함수는 LangGraph Native `astream_events` API를 사용하여
    이벤트 스트림에서 모델 스트림 이벤트(`on_chat_model_stream`)만 추출하고,
    나머지 이벤트는 내부 관측성 로그로만 기록한다.

    Graceful Teardown:
        클라이언트 연결 종료(asyncio.CancelledError)는 조용히 정리하고 스트림을 종료한다.
        기타 예외는 `[STREAM][ERROR]` 로그 후 `ErrorChunk`를 발행하고 스트림을 종료한다.

    Args:
        graph: 실행할 LangGraph CompiledStateGraph 인스턴스.
        inputs: 그래프 실행에 전달할 입력 딕셔너리.
        config: LangGraph RunnableConfig (thread_id 등 포함).
        stream_version: astream_events API 버전. 기본값은 공통 상수에서 로드.

    Yields:
        StreamChunk: TokenChunk (토큰) | DoneChunk (완료) | ErrorChunk (오류)
    """
    try:
        async for event in graph.astream_events(
            inputs,
            config=config,
            version=stream_version,
        ):
            event_name: str = event.get("event", "")
            chunk_data = event.get("data", {})

            # 모델 스트림 이벤트만 추출하여 TokenChunk 발행
            if event_name in (
                _LANGGRAPH_EVENT_ON_CHAT_MODEL_STREAM,
                _LANGGRAPH_EVENT_ON_LLM_STREAM,
            ):
                chunk = chunk_data.get(_CHUNK_KEY)
                if chunk is None:
                    continue

                content = getattr(chunk, _CONTENT_KEY, None)
                if not isinstance(content, str) or not content:
                    continue

                yield TokenChunk(data=content)

            else:
                # 비스트림 이벤트: 내부 관측성 로그로만 기록 (클라이언트에 미노출)
                logger.debug(
                    "[STREAM][INTERNAL] event=%r (not forwarded to client)",
                    event_name,
                )

    except asyncio.CancelledError:
        # 클라이언트 연결 종료 — 조용히 정리(Graceful Teardown)
        logger.info(
            "[STREAM] Client disconnected. Graceful teardown initiated."
        )
        # CancelledError를 재발생시켜 상위 태스크가 올바르게 취소될 수 있도록 함
        raise

    except Exception as exc:  # noqa: BLE001
        # 예상치 못한 예외: 로그 후 ErrorChunk 발행 및 스트림 종료
        # PII 마스킹은 ErrorChunk.message의 @field_validator가 자동 적용
        logger.error(
            "[STREAM][ERROR] Unexpected error during streaming: type=%s",
            type(exc).__name__,
            exc_info=True,
        )
        yield ErrorChunk(
            code=_ERROR_CODE_STREAM_ERROR,
            message=str(exc),  # @field_validator가 mask_pii_id() 자동 적용
        )
        return

    # 스트림 정상 완료
    yield DoneChunk()

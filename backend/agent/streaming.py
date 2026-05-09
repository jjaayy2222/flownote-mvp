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
from collections.abc import AsyncIterator, Mapping
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError

from backend.core.config.streaming import (
    STREAMING_DEFAULT_STREAM_VERSION,
    StreamVersion,
)
from backend.schemas.streaming import (
    DoneChunk,
    ErrorChunk,
    StreamChunk,
    TokenChunk,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LangGraph 이벤트 스키마 타입 정의 (TypedDict)
# 느슨한 Mapping[str, Any] 대신 이벤트 계약을 명시적으로 문서화
# total=False: LangGraph가 새로운 필드를 추가할 수 있어 선택적 필드로 보수적으로 처리
# ─────────────────────────────────────────────────────────────────────────────


class _StreamEventData(TypedDict, total=False):
    """
    LangGraph astream_events 이벤트의 `data` 필드 예상 구조.
    스트리밍 이벤트에서는 `chunk` 키에 AIMessage-류 객체가 담김.
    """

    chunk: Any


class _StreamEvent(TypedDict, total=False):
    """
    LangGraph `astream_events` v2가 발행하는 이벤트 구조.
    표준 필드를 명시적으로 문서화하여 이벤트 스키마 변경 시 조기 감지를 돕는다.
    """

    event: str
    data: _StreamEventData
    name: str
    run_id: str
    tags: list[str]
    metadata: dict[str, Any]

# ─────────────────────────────────────────────────────────────────────────────
# LangGraph 이벤트 타입 상수 (문자열 하드코딩 방지)
# LangGraph astream_events v2 기준 이벤트 이름
# ─────────────────────────────────────────────────────────────────────────────

_LANGGRAPH_EVENT_ON_CHAT_MODEL_STREAM: str = "on_chat_model_stream"
_LANGGRAPH_EVENT_ON_LLM_STREAM: str = "on_llm_stream"

# 토큰 청크 데이터 접근 키
_CHUNK_KEY: str = "chunk"
_CONTENT_KEY: str = "content"
_EVENT_NAME_KEY: str = "event"
_EVENT_DATA_KEY: str = "data"

# 에러 코드 상수 (하드코딩 방지)
_ERROR_CODE_STREAM_ERROR: str = "STREAM_ERROR"
_ERROR_CODE_RECURSION_LIMIT: str = "RECURSION_LIMIT"

# 클라이언트에 전달할 일반화된 에러 메시지
# 내부 구현 세부사항(스택 트레이스, 경로 등) 노출 방지 — Information Disclosure 예방
_GENERIC_STREAM_ERROR_MESSAGE: str = (
    "Unexpected error occurred during streaming. Please try again later."
)
_RECURSION_LIMIT_MESSAGE: str = (
    "The response could not be completed due to a processing limit. "
    "Please try a shorter or simpler query."
)


# ─────────────────────────────────────────────────────────────────────────────
# 이벤트 파싱 헬퍼
# ─────────────────────────────────────────────────────────────────────────────


def _extract_token_from_event(event: Mapping[str, Any]) -> str | None:
    """
    LangGraph 스트림 이벤트에서 토큰 텍스트를 추출한다.

    이벤트 구조에 대한 가정을 한 곳에 집중하여, 이벤트 스키마 변경 시
    수정 지점을 최소화하고 단위 테스트를 용이하게 한다.

    예상 이벤트 구조: _StreamEvent TypedDict 참조 (문서화 목적).
    LangGraph가 실제로 반환하는 타입은 CustomStreamEvent | StandardStreamEvent
    Union이므로, 런타임 호환성을 위해 파라미터는 Mapping[str, Any]를 사용한다.

    Args:
        event: LangGraph astream_events가 발행하는 이벤트 딕셔너리.

    Returns:
        추출된 토큰 텍스트(str). 토큰이 없거나 비어 있으면 None.
    """
    event_name: str = event.get(_EVENT_NAME_KEY, "")

    # 모델 스트림 이벤트가 아니면 토큰 없음
    if event_name not in (
        _LANGGRAPH_EVENT_ON_CHAT_MODEL_STREAM,
        _LANGGRAPH_EVENT_ON_LLM_STREAM,
    ):
        return None

    # data 필드 방어적 처리 — 세 단계 검증 (정상 스킵 vs 비정상 None 구분)
    # 1단계: data 키 자체가 없음 → 조용히 건너뜀 (정상적인 비-스트리밍 이벤트)
    # 2단계: data 키는 있으나 값이 명시적 None → 스키마 이상 신호이므로 warning
    # 3단계: data 값이 비-Mapping → 스키마 이상 신호이므로 warning
    run_id: str = event.get("run_id", "")  # 진단용 세션 식별자 (원문 노출 없이 컨텍스트 제공)
    
    if _EVENT_DATA_KEY not in event:
        # data 키가 아예 없는 이벤트: 정상 케이스로 간주
        return None
        
    raw_data = event[_EVENT_DATA_KEY]
    if raw_data is None:
        logger.warning(
            "[STREAM][SCHEMA] Explicit data=None in streaming event '%s' "
            "(run_id=%s). Possible schema change.",
            event_name,
            run_id,
        )
        return None
        
    if not isinstance(raw_data, Mapping):
        logger.warning(
            "[STREAM][SCHEMA] Unexpected data type in streaming event '%s' "
            "(run_id=%s): expected Mapping, got %s. Possible schema change.",
            event_name,
            run_id,
            type(raw_data).__name__,
        )
        return None

    chunk_data: _StreamEventData = cast(_StreamEventData, raw_data)
    chunk = chunk_data.get(_CHUNK_KEY)
    if chunk is None:
        logger.warning(
            "[STREAM][SCHEMA] No '%s' key in data of streaming event '%s' "
            "(run_id=%s). Possible schema change.",
            _CHUNK_KEY,
            event_name,
            run_id,
        )
        return None


    content = getattr(chunk, _CONTENT_KEY, None)
    if not isinstance(content, str) or not content:
        return None

    return content


# ─────────────────────────────────────────────────────────────────────────────
# 메인 스트리밍 어댑터
# ─────────────────────────────────────────────────────────────────────────────


async def stream_agent_response(
    graph: CompiledStateGraph,
    inputs: Mapping[str, Any],
    config: RunnableConfig,
    *,
    stream_version: StreamVersion = STREAMING_DEFAULT_STREAM_VERSION,
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
            token = _extract_token_from_event(event)
            if token is not None:
                yield TokenChunk(data=token)
            else:
                # 비스트림 이벤트: 내부 관측성 로그로만 기록 (클라이언트에 미노출)
                logger.debug(
                    "[STREAM][INTERNAL] event=%r (not forwarded to client)",
                    event.get(_EVENT_NAME_KEY, ""),
                )

    except asyncio.CancelledError:
        # 클라이언트 연결 종료 — 조용히 정리(Graceful Teardown)
        logger.info(
            "[STREAM] Client disconnected. Graceful teardown initiated."
        )
        # CancelledError를 재발생시켜 상위 태스크가 올바르게 취소될 수 있도록 함
        raise

    except GraphRecursionError as exc:
        # LangGraph 재귀 한계 초과 — 알려진 운영 오류로 별도 처리
        logger.warning(
            "[STREAM][RECURSION] GraphRecursionError during streaming: %s",
            type(exc).__name__,
        )
        yield ErrorChunk(
            code=_ERROR_CODE_RECURSION_LIMIT,
            message=_RECURSION_LIMIT_MESSAGE,
        )
        return

    except Exception as exc:  # noqa: BLE001
        # 예상치 못한 예외: 서버 로그에는 상세 정보 기록, 클라이언트에는 일반화된 메시지만 전달
        # 내부 에러 메시지/스택 트레이스의 클라이언트 노출은 Information Disclosure 위험이므로
        # str(exc)는 로그에만 남기고 _GENERIC_STREAM_ERROR_MESSAGE를 클라이언트에 발행
        logger.error(
            "[STREAM][ERROR] Unexpected error during streaming: type=%s, detail=%s",
            type(exc).__name__,
            str(exc),  # 상세 에러 정보는 서버 로그에만 기록
            exc_info=True,
        )
        yield ErrorChunk(
            code=_ERROR_CODE_STREAM_ERROR,
            # 클라이언트에는 일반화된 메시지만 전달 (구현 세부사항 비노출)
            message=_GENERIC_STREAM_ERROR_MESSAGE,
        )
        return

    # 스트림 정상 완료
    yield DoneChunk()


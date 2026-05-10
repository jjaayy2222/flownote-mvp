# backend/api/endpoints/chat_stream.py

import logging
import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from backend.api.models import ChatQueryRequest
from backend.utils import get_chat_log_extra
from backend.core.config.streaming import STREAMING_DEFAULT_TIMEOUT_SECS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat-stream"])


@router.post(
    "/stream",
    summary="RAG 채팅 결과 스트리밍 (SSE)",
    description="사용자의 질문을 기반으로 RAG 파이프라인을 거쳐 응답을 Server-Sent Events(SSE) 형식으로 반환합니다.",
)
async def stream_chat_endpoint(
    request: Request,
    body: ChatQueryRequest,
) -> EventSourceResponse:
    """
    SSE 기반 스트리밍 엔드포인트 스캐폴딩.
    """

    # 디버깅 및 트레이싱을 위한 최소 로그 (PII 마스킹 적용)
    # body.user_id가 누락되거나 None인 경우에 대비하여 안전하게 처리합니다.
    logger.info(
        "Received streaming chat request",
        extra=get_chat_log_extra(body),
    )
    
    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            # 1단계 스캐폴딩: 추후 LangGraph 에이전트 스트리밍 큐와 연동될 예정
            # 현재는 연결 확인을 위한 간단한 더미 이벤트를 전송합니다.
            yield {
                "event": "message",
                "data": json.dumps({
                    "status": "connected",
                    "message": "Streaming endpoint scaffolded successfully."
                }),
            }
            
            # 클라이언트 연결 종료 감지를 위한 임시 대기 (asyncio.wait_for 활용)
            # 주의: 이는 스캐폴딩 상태에서의 '하드 타임아웃(최대 연결 유지 시간)' 제한입니다.
            # 추후 실제 LangGraph 구현이 연동되면, 무조건적인 종료가 아닌 
            # '마지막 청크 전송 이후의 유휴 시간(Idle Timeout)'을 기준으로 폴링이 종료되도록 변경해야 합니다.
            async def check_disconnect() -> None:
                while not await request.is_disconnected():
                    await asyncio.sleep(5)
                    
            try:
                await asyncio.wait_for(check_disconnect(), timeout=STREAMING_DEFAULT_TIMEOUT_SECS)
                logger.info("[STREAM] Client disconnected.")
            except asyncio.TimeoutError:
                logger.warning("[STREAM] Connection timed out due to inactivity.")
                
        except asyncio.CancelledError:
            logger.info("[STREAM] Request was cancelled.")
            raise
        except Exception as e:
            logger.error(f"[STREAM] Unexpected error in streaming endpoint: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": "Internal Server Error"}),
            }

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

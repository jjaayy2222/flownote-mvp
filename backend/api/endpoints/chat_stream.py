# backend/api/endpoints/chat_stream.py

import logging
import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from backend.api.models import ChatQueryRequest

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
    
    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            # 1단계 스캐폴딩: 추후 LangGraph 에이전트 스트리밍 큐와 연동될 예정
            # 현재는 연결 확인을 위한 간단한 더미 이벤트를 전송합니다.
            yield {
                "event": "message",
                "data": '{"status": "connected", "message": "Streaming endpoint scaffolded successfully."}',
            }
            
            # 클라이언트 연결 종료 감지를 위한 임시 대기 (추후 백프레셔 큐 기반 폴링으로 대체)
            while True:
                if await request.is_disconnected():
                    logger.info("[STREAM] Client disconnected.")
                    break
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("[STREAM] Request was cancelled.")
            raise
        except Exception as e:
            logger.error(f"[STREAM] Unexpected error in streaming endpoint: {e}")
            yield {
                "event": "error",
                "data": '{"error": "Internal Server Error"}',
            }

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

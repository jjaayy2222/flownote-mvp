# backend/api/endpoints/chat_stream.py

import logging
import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request, HTTPException
from sse_starlette.sse import EventSourceResponse

from backend.api.models import ChatQueryRequest
from backend.utils import mask_pii_id
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

    # 기본 스키마 검증: 필수 필드 확인 및 간단한 내용 검증
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail="`query`는 비어 있을 수 없습니다.")

    # 디버깅 및 트레이싱을 위한 최소 로그 (PII 마스킹 적용)
    truncated_query = body.query[:200] + ("..." if len(body.query) > 200 else "")
    logger.info(
        "Received streaming chat request",
        extra={
            "user_id_hash": mask_pii_id(body.user_id),
            "query_preview": truncated_query,
        },
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
            
            # 클라이언트 연결 종료 감지를 위한 임시 대기 (최대 타임아웃 적용)
            for _ in range(STREAMING_DEFAULT_TIMEOUT_SECS):
                if await request.is_disconnected():
                    logger.info("[STREAM] Client disconnected.")
                    break
                await asyncio.sleep(1)
            else:
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

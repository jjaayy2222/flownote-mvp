# backend/api/endpoints/chat.py

"""
스트리밍 기반 AI 채팅 엔드포인트
"""

import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.api.models import ChatQueryRequest
from backend.services.chat_service import ChatService, get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream", summary="RAG 채팅 결과 스트리밍")
async def stream_chat(
    request: ChatQueryRequest, chat_service: ChatService = Depends(get_chat_service)
):
    """
    사용자의 질문을 기반으로 RAG 파이프라인(LangChain + Hybrid Search)을 거쳐
    LLM의 응답을 Server-Sent Events(SSE) 스트리밍 형식으로 반환합니다.
    """
    logger.info(
        "Chat stream requested by user: %s (query_len=%d)",
        request.user_id,
        len(request.query),
    )

    return StreamingResponse(
        chat_service.stream_chat(
            query=request.query,
            user_id=request.user_id,
            session_id=request.session_id,
            k=request.k,
            alpha=request.alpha,
        ),
        media_type="text/event-stream",
    )

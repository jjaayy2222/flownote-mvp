# backend/api/endpoints/chat.py

"""
스트리밍 기반 AI 채팅 엔드포인트
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.models import ChatQueryRequest, ChatHistoryResponse
from backend.services.chat_service import ChatService, get_chat_service
from backend.services.chat_history_service import (
    ChatHistoryService,
    get_chat_history_service,
)

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
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/history/{session_id}",
    response_model=ChatHistoryResponse,
    summary="대화 히스토리 조회",
)
async def get_chat_history(
    session_id: str,
    limit: int = 20,
    chat_history_service: ChatHistoryService = Depends(get_chat_history_service),
):
    """
    지정된 세션 ID의 최근 대화 내역을 조회합니다.
    """
    try:
        messages = await chat_history_service.get_history(session_id, limit=limit)
        return ChatHistoryResponse(
            status="success", session_id=session_id, messages=messages
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/history/{session_id}", summary="대화 히스토리 초기화")
async def clear_chat_history(
    session_id: str,
    chat_history_service: ChatHistoryService = Depends(get_chat_history_service),
):
    """
    지정된 세션 ID의 대화 내역을 모두 삭제합니다.
    """
    try:
        await chat_history_service.clear_history(session_id)
        return {
            "status": "success",
            "message": f"History for session {session_id} cleared.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

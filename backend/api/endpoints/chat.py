# backend/api/endpoints/chat.py

"""
스트리밍 기반 AI 채팅 엔드포인트
"""

import logging
from fastapi import APIRouter, Depends, HTTPException

from fastapi.responses import StreamingResponse

from backend.api.models import (
    ChatQueryRequest,
    ChatHistoryResponse,
    SessionListResponse,
    ChatSessionMeta,
    RenameSessionRequest,
)
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


# ─────────────────────────────────────────────────────────────
# History endpoints (기존)
# ─────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────
# Session management endpoints (Issue #776 신규)
# ─────────────────────────────────────────────────────────────


@router.post(
    "/sessions",
    summary="세션 등록 또는 갱신",
)
async def register_session(
    session_id: str,
    user_id: str,
    name: str | None = None,
    chat_history_service: ChatHistoryService = Depends(get_chat_history_service),
):
    """
    세션 메타데이터(session_id, user_id, name)를 Redis에 등록하거나 갱신합니다.
    채팅창이 처음 열릴 때 또는 새 세션이 생성될 때 호출합니다.
    """
    try:
        await chat_history_service.register_session(
            session_id=session_id,
            user_id=user_id,
            name=name,
        )
        return {"status": "success", "session_id": session_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="사용자 세션 목록 조회",
)
async def list_sessions(
    user_id: str,
    chat_history_service: ChatHistoryService = Depends(get_chat_history_service),
):
    """
    지정된 user_id의 세션 목록을 최근 활성순으로 반환합니다.
    """
    try:
        sessions_raw = await chat_history_service.list_sessions(user_id=user_id)
        sessions = [ChatSessionMeta(**s) for s in sessions_raw]
        return SessionListResponse(
            status="success",
            user_id=user_id,
            sessions=sessions,
            count=len(sessions),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/sessions/{session_id}/name",
    summary="세션 이름 수정",
)
async def rename_session(
    session_id: str,
    body: RenameSessionRequest,
    chat_history_service: ChatHistoryService = Depends(get_chat_history_service),
):
    """
    특정 세션의 표시 이름을 수정합니다.
    """
    try:
        success = await chat_history_service.rename_session(
            session_id=session_id,
            name=body.name,
        )
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session '{session_id}' not found.",
            )
        return {"status": "success", "session_id": session_id, "name": body.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

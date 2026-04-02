# backend/api/endpoints/chat.py

"""
스트리밍 기반 AI 채팅 엔드포인트
"""

import logging
import os
import time
import threading
from collections import OrderedDict
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request  # type: ignore[import]

from fastapi.responses import StreamingResponse  # type: ignore[import]

from backend.api.models import (  # type: ignore[import]
    ChatQueryRequest,
    ChatHistoryResponse,
    SessionListResponse,
    ChatSessionMeta,
    RenameSessionRequest,
    FeedbackRequest,
    FeedbackResponse,
    FeedbackStatsResponse,
)
from backend.services.chat_service import ChatService, get_chat_service  # type: ignore[import]
from backend.services.chat_history_service import (  # type: ignore[import]
    ChatHistoryService,
    get_chat_history_service,
    MAX_FEEDBACK_STATS_LIMIT,
)
from backend.config import AdminConfig, AlertConfig
from backend.utils import mask_pii_id  # type: ignore[import]

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
# RedisUnavailableError → 503 변환은 main.py의 전역 핸들러에서 처리
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
    user_id: Optional[str] = None,
    chat_history_service: ChatHistoryService = Depends(get_chat_history_service),
):
    """
    지정된 세션 ID의 대화 내역과 세션 메타데이터를 완전 삭제합니다.
    user_id를 함께 전달하면 세션 목록(ZSET)에서도 제거됩니다.
    """
    try:
        await chat_history_service.clear_history(session_id, user_id=user_id)
        return {
            "status": "success",
            "message": f"Session {session_id} cleared.",
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


# ─────────────────────────────────────────────────────────────
# Observability / Feedback endpoints (Issue #777)
# ─────────────────────────────────────────────────────────────


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    summary="AI 응답 피드백 수집",
)
async def submit_feedback(
    body: FeedbackRequest,
    chat_history_service: ChatHistoryService = Depends(get_chat_history_service),
):
    """
    사용자의 AI 답변 평가(Thumbs up/down) 및 코멘트를 수집합니다.
    Redis Hash 구조를 통해 메시지 단위 식별 저장 및 실시간 조회 보장
    """
    # 1. Observability 목적으로 정형화된 로그(Structured log) 기록
    comment_length: int = len(body.feedback_text) if body.feedback_text else 0
    
    logger.info(
        "[OBS] Event: Feedback received",
        extra={
            "session_id_hash": mask_pii_id(body.session_id),
            "message_id_hash": mask_pii_id(body.message_id),
            "rating": body.rating,
            "has_comment": bool(body.feedback_text),
            "comment_length": comment_length,
        },
    )

    # 2. Redis 피드백 저장 (DB 매핑 테이블 대신 O(1) Redis Hash 사용)
    try:
        await chat_history_service.save_feedback(
            session_id=body.session_id,
            message_id=body.message_id,
            rating=body.rating,
            feedback_text=body.feedback_text,
        )
    except Exception as e:
        # 저장이 실패하더라도 로깅은 완료되었으므로 사용자측엔 200 반환 후 백그라운드 [OBS] 알림
        logger.error(
            f"[OBS] Error: Failed to save feedback to Redis: {e}",
            extra={
                "session_id_hash": mask_pii_id(body.session_id),
                "message_id_hash": mask_pii_id(body.message_id)
            }
        )

    return FeedbackResponse(
        status="success",
        message_id=body.message_id,
        rating=body.rating,
    )


# 인메모리 테스트 알림 Rate Limiting 상태 (IP 기반 추적)
# 인메모리 테스트 알림 Rate Limiting 상태 (IP 기반 추적)
# key: IP, value: timestamp (monotonic)
_test_alert_history: OrderedDict[str, float] = OrderedDict()
_TEST_ALERT_THROTTLE_SECONDS = 30.0
_TEST_ALERT_MAX_ENTRIES = 1000

# 동시성 환경 레이스 컨디션 방지를 위한 모듈 레벨 락
_test_alert_lock = threading.Lock()

# 신뢰할 수 있는 프록시 IP 목록 (실제 환경에서는 환경변수나 설정값으로 분리)
_TRUSTED_PROXIES = {"127.0.0.1", "::1", "localhost"}

def _cleanup_test_alert_history(now: float) -> None:
    """오래된 엔트리를 제거하고 최대 크기를 넘기면 가장 오래된 항목부터 삭제하여 메모리 릭을 방지합니다.

    OrderedDict 기반 LRU로, 개별 삭제 연산은 O(1)이지만 한 번의 호출에서
    만료된 항목 또는 초과된 항목 수만큼 최대 O(N)까지 스캔/삭제가 발생할 수 있습니다.
    따라서 전체적으로는 항목 수에 대해 상한이 있는, 분할 상환(Amortized) O(1) 복잡도를 갖습니다.
    """
    global _test_alert_history
    cutoff = now - _TEST_ALERT_THROTTLE_SECONDS
    
    # 1) 만료된 항목 삭제 (분할 상환 O(1))
    while _test_alert_history:
        ip, ts = next(iter(_test_alert_history.items()))
        if ts < cutoff:
            _test_alert_history.pop(ip)
        else:
            break
            
    # 2) 허용된 최대 튜플 크기를 초과할 경우, 가장 오래된 항목 삭제 (개별 연산 O(1))
    while len(_test_alert_history) > _TEST_ALERT_MAX_ENTRIES:
        _test_alert_history.popitem(last=False)

def get_client_ip(request: Request) -> str:
    """신뢰할 수 있는 프록시에 한하여 X-Forwarded-For 헤더를 사용함으로써 IP 스푸핑을 방지합니다."""
    client_ip = request.client.host if request.client else "unknown"

    if client_ip in _TRUSTED_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For의 가장 첫 번째 값(가장 좌측)은 최초 발신지(Original Client) IP이며,
            # 이는 신뢰할 수 있는 프록시(_TRUSTED_PROXIES)를 거친 경우에만 위조되지 않은 것으로 간주하여 신뢰합니다.
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

    return client_ip

@router.post(
    "/alert/test",
    summary="Discord 알림 테스트 발송 (Admin)",
)
async def test_alert_endpoint(
    request: Request,
    x_admin_key: Optional[str] = Header(None, description="Next.js 프록시 내부 인증 키"),
):
    """
    강제로 [OBS] 로그를 발생시켜 Discord 알림 파이프라인이 작동하는지 테스트합니다.
    """
    admin_key = AdminConfig.get_admin_key()
    
    if not admin_key or x_admin_key != admin_key:
        logger.warning("[OBS] Unauthorized attempt to trigger alert test.")
        raise HTTPException(status_code=403, detail="Forbidden")

    current_time = time.monotonic()
    client_ip = get_client_ip(request)

    # [Fix] 락을 통한 동시성 레이스 컨디션 완벽 방어 처리
    with _test_alert_lock:
        # [Fix] 메모리 릭 방지를 위한 Eviction 적용 (분할 상환 O(1))
        _cleanup_test_alert_history(current_time)
        
        # [Fix] 개별 클라이언트 IP 기반 Rate Limiting 
        last_called = _test_alert_history.get(client_ip, 0.0)
        if current_time - last_called < _TEST_ALERT_THROTTLE_SECONDS:
            logger.warning(f"[OBS] Rate limited: Test alert requested too frequently by IP: {client_ip}")
            raise HTTPException(status_code=429, detail="Too Many Requests. Please wait before testing again.")

        _test_alert_history[client_ip] = current_time
        _test_alert_history.move_to_end(client_ip)  # 최근 접속한 항목을 뒤로 보내 LRU 체계를 확립

    # 強제 [OBS] Warning 발생 -> DiscordAlertHandler가 가로챔 (호출자 IP 메타데이터 포함)
    logger.warning(f"[OBS] 🔔 Test Alert: 관리자 페이지에서 테스트 알림이 요청되었습니다. (IP: {client_ip})")
    
    return {"status": "success", "message": "Test alert triggered."}


@router.get(
    "/feedback/stats",
    response_model=FeedbackStatsResponse,
    summary="AI 피드백 통계 및 트렌드 데이터 조회 (Admin)",
)
async def get_feedback_stats_endpoint(
    limit: int = Query(50, ge=1, le=MAX_FEEDBACK_STATS_LIMIT, description=f"최근 피드백 반환 최대 개수 (상한 {MAX_FEEDBACK_STATS_LIMIT})"),
    x_admin_key: Optional[str] = Header(None, description="Next.js 프록시 내부 인증 키"),
    chat_history_service: ChatHistoryService = Depends(get_chat_history_service),
):
    """
    어드민 대시보드 시각화를 위한 피드백 통계를 반환합니다.
    
    - O(N) SCAN 기반 전체 피드백 Hash 순회
    - 일자별 긍정/부정 트렌드 차트 데이터를 위해 집계
    - 최신 사용자 피드백 텍스트 리스트(최대 limit개) 추출
    """
    
    # 설정 관리자를 통해 인증 키 조회 (핫 리로드 및 테스트 유연성 보장)
    admin_key = AdminConfig.get_admin_key()
    
    if not admin_key:
        logger.error("[OBS] ADMIN_API_KEY is not configured in environment. Rejecting access.")
        raise HTTPException(status_code=500, detail="Server Configuration Error: Missing Secret")
        
    if not x_admin_key or x_admin_key != admin_key:
        logger.warning("[OBS] Unauthorized attempt to access admin stats endpoint.")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Admin Key")
    
    try:
        stats = await chat_history_service.get_feedback_stats(limit_recent=limit)
        return FeedbackStatsResponse(
            status="success",
            total_up=stats["total_up"],
            total_down=stats["total_down"],
            trends=stats["trends"],
            recent_feedbacks=stats["recent_feedbacks"],
            is_monitoring_active=bool(AlertConfig.DISCORD_WEBHOOK_URL),
        )

    except Exception as e:
        logger.error(f"[OBS] Error fetching feedback stats: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

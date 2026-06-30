# backend/api/routes.py

"""
중앙 집중식 API 라우터 엔트리포인트 모듈입니다.
이 모듈은 FastAPI 애플리케이션의 모든 하위 도메인 라우터를 단일 `APIRouter` 인스턴스(`router`)로
통합하여 `prefix="/api"`를 기준으로 마운트합니다.

Centralized API router entry point module.
This module aggregates all domain-specific sub-routers into a single
`APIRouter` instance (`router`) mounted under the `/api` prefix.

포함된 도메인 라우터 (Included Domain Routers):
    - `/classify` : 분류(Classification) 관련 엔드포인트
    - `/search`   : 검색(Search, 하이브리드 RAG) 관련 엔드포인트
    - `/metadata` : 파일 메타데이터 처리 엔드포인트
    - `/chat`     : 채팅(Chat) 및 세션 관리 엔드포인트
    - `/chat`     : 채팅 스트리밍(SSE) 엔드포인트
    - `/admin`    : 어드민 전용 관리 엔드포인트
    - `/privacy`  : GDPR 기반 개인정보 삭제권(Right-to-Erasure) 엔드포인트
"""

from fastapi import APIRouter, Depends

from ..services.i18n_service import get_message
from . import endpoints
from .deps import get_locale
from .models import HealthCheckResponse

router = APIRouter(prefix="/api")


# Health check endpoint
@router.get("/health", response_model=HealthCheckResponse)
async def health_check(locale: str = Depends(get_locale)) -> HealthCheckResponse:
    """
    서버 상태를 확인하는 헬스체크 엔드포인트입니다.
    클라이언트의 `Accept-Language` 헤더를 기반으로 `get_locale` 의존성을 통해 로케일을 주입받으며,
    다국어(i18n)로 응답 메시지를 반환합니다.

    Health check endpoint that confirms the server is running and responsive.
    It injects the locale based on the client's `Accept-Language` header
    via the `get_locale` dependency, returning an i18n response message.

    Args:
        locale (str): FastAPI `get_locale` 의존성을 통해 주입된 로케일 코드 (예: 'ko', 'en').

    Returns:
        HealthCheckResponse: 서버 상태(`status`)와 다국어 메시지(`message`)가 포함된 응답 객체.
    """
    return HealthCheckResponse(
        status="success", message=get_message("status_ok", locale)
    )


# 도메인별 하위 라우터 등록
# [분류] 노트/파일 분류 관련 엔드포인트
router.include_router(endpoints.classify_router)
# [검색] 하이브리드 RAG 검색 엔드포인트
router.include_router(endpoints.search_router)
# [메타데이터] 파일 메타데이터 처리 엔드포인트
router.include_router(endpoints.metadata_router)
# [채팅] 채팅, 대화 히스토리 및 세션 관리 엔드포인트
router.include_router(endpoints.chat_router)
# [채팅 스트리밍] SSE 기반 실시간 채팅 스트리밍 엔드포인트
router.include_router(endpoints.chat_stream_router)
# [어드민] 내부 운영 전용 관리자 엔드포인트
router.include_router(endpoints.admin_router)

# [개인정보] GDPR 삭제권(Right-to-Erasure) 엔드포인트
# 참조: backend.core.audit_logger.schedule_audit_log_cleanup (등록 위치: backend/main.py lifespan)
router.include_router(endpoints.privacy_router)

# backend/api/endpoints/__init__.py

"""
도메인별 FastAPI 라우터 서브모듈을 집계하여 외부로 노출하는 패키지 초기화 모듈입니다.
Package initializer that aggregates domain-specific FastAPI router sub-modules.

각 서브모듈의 `router` 인스턴스를 `*_router` 별칭으로 노출하여,
`backend.api.routes` 에서 단일 진입점으로 등록할 수 있게 합니다.
Each sub-module's `router` instance is re-exported under a `*_router` alias,
allowing `backend.api.routes` to register them through a single entry point.

노출되는 라우터:
    - classify_router   : 분류(Classification) 도메인
    - search_router     : 검색(Search) 도메인
    - metadata_router   : 메타데이터(Metadata) 도메인
    - automation_router : 자동화(Automation) 도메인
    - chat_router       : 채팅(Chat) 도메인
    - chat_stream_router: 채팅 스트리밍(SSE) 도메인
    - admin_router      : 어드민(Admin) 도메인
    - privacy_router    : 개인정보(Privacy, GDPR) 도메인
"""

from .admin import router as admin_router
from .automation import router as automation_router
from .chat import router as chat_router
from .chat_stream import router as chat_stream_router
from .classify import router as classify_router
from .metadata import router as metadata_router
from .privacy import router as privacy_router
from .search import router as search_router

__all__ = [
    "classify_router",
    "search_router",
    "metadata_router",
    "automation_router",
    "chat_router",
    "chat_stream_router",
    "admin_router",
    "privacy_router",
]

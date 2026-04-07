# backend/api/endpoints/__init__.py

"""Endpoints Module"""

from .classify import router as classify_router
from .search import router as search_router
from .metadata import router as metadata_router
from .automation import router as automation_router
from .chat import router as chat_router
from .admin import router as admin_router

__all__ = [
    "classify_router",
    "search_router",
    "metadata_router",
    "automation_router",
    "chat_router",
    "admin_router",
]

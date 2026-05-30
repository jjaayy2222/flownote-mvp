# backend/graph/__init__.py

"""
지식 그래프 Repository 추상화 계층 (Phase 4-1).

공개 API:
    AbstractGraphRepository   — 엔진 불가지론적 인터페이스
    NetworkXGraphRepository   — networkx 기반 인메모리/파일시스템 구현체
    build_graph_path          — 테넌트 격리 경로 빌더 (공유 헬퍼)
"""

from backend.graph.base import AbstractGraphRepository
from backend.graph.networkx_repository import NetworkXGraphRepository
from backend.graph.path_utils import build_graph_path

__all__ = [
    "AbstractGraphRepository",
    "NetworkXGraphRepository",
    "build_graph_path",
]

# backend/graph/__init__.py

"""
지식 그래프 Repository 추상화 계층 (Phase 4-1) 및 파이프라인.

공개 API:
    AbstractGraphRepository   — 엔진 불가지론적 인터페이스
    NetworkXGraphRepository   — networkx 기반 인메모리/파일시스템 구현체
    build_graph_path          — 테넌트 격리 경로 빌더 (공유 헬퍼)
    EntityEdgeExtractor       — 마크다운 및 LLM 기반 명시/암묵적 엣지 추출기
    find_orphan_nodes         — 고립 노트(Orphan Notes) 감지 알고리즘 (Phase 4-4)
"""

from backend.graph.analysis import find_orphan_nodes, get_orphan_degree_threshold
from backend.graph.base import AbstractGraphRepository
from backend.graph.networkx_repository import NetworkXGraphRepository
from backend.graph.path_utils import build_graph_path
from backend.graph.extractor import EntityEdgeExtractor

__all__ = [
    "AbstractGraphRepository",
    "NetworkXGraphRepository",
    "build_graph_path",
    "EntityEdgeExtractor",
    "find_orphan_nodes",
    "get_orphan_degree_threshold",
]


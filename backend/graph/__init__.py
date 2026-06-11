# backend/graph/__init__.py

"""
지식 그래프 Repository 추상화 계층 (Phase 4-1) 및 파이프라인.

공개 API:
    AbstractGraphRepository   — 엔진 불가지론적 인터페이스
    NetworkXGraphRepository   — networkx 기반 인메모리/파일시스템 구현체 (networkx 설치 필요)
    build_graph_path          — 테넌트 격리 경로 빌더 (공유 헬퍼)
    EntityEdgeExtractor       — 마크다운 및 LLM 기반 명시/암묵적 엣지 추출기
    find_orphan_nodes         — 고립 노트(Orphan Notes) 감지 알고리즘 (Phase 4-4)
    find_link_recommendations — 벡터 유사도 기반 연결 추천 쌍 발굴 (Phase 4-4 3단계)
    send_link_recommendations — 연결 추천 앱 내 알림 전송 (Phase 4-4 3단계)
"""

from backend.graph.analysis import find_orphan_nodes, get_orphan_degree_threshold
from backend.graph.base import AbstractGraphRepository
from backend.graph.path_utils import build_graph_path
from backend.graph.extractor import EntityEdgeExtractor
from backend.graph.similarity import find_link_recommendations, get_link_similarity_threshold
from backend.graph.notifications import send_link_recommendations

# NetworkXGraphRepository는 networkx 패키지가 설치된 경우에만 로드
# (requirements.txt에 networkx가 없는 환경에서도 나머지 모듈이 정상 동작하도록 보호)
try:
    from backend.graph.networkx_repository import NetworkXGraphRepository
except ImportError:
    NetworkXGraphRepository = None  # type: ignore[assignment,misc]

__all__ = [
    "AbstractGraphRepository",
    "NetworkXGraphRepository",
    "build_graph_path",
    "EntityEdgeExtractor",
    "find_orphan_nodes",
    "get_orphan_degree_threshold",
    "find_link_recommendations",
    "get_link_similarity_threshold",
    "send_link_recommendations",
]

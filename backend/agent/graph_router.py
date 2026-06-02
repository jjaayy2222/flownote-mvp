# backend/agent/graph_router.py

import logging
from typing import Any, Dict, List, Optional

from backend.core.health_registry import HealthRegistry
from backend.core.config_validator import Subsystem

logger = logging.getLogger(__name__)

class GraphHybridRouter:
    """
    기존 벡터 검색(Vector RAG) 결과와 지식 그래프 탐색 결과를 결합하는 하이브리드 쿼리 라우터.
    """
    
    def __init__(self, health_registry: Optional[HealthRegistry] = None) -> None:
        self.health_registry = health_registry or HealthRegistry.get_instance()

    def route_query(self, query: str, vector_results: List[Dict[str, Any]], **kwargs: Any) -> List[Dict[str, Any]]:
        """
        벡터 검색 결과(vector_results)를 입력받아 그래프 탐색과 결합하여 하이브리드 결과를 반환한다.
        """
        # [핵심] 매 쿼리마다 HealthRegistry.is_ok(Subsystem.GRAPH_ENGINE)를 최우선 검사
        if not self.health_registry.is_ok(Subsystem.GRAPH_ENGINE):
            summary = self.health_registry.get_summary()
            current_status = summary.get(Subsystem.GRAPH_ENGINE.value, "UNKNOWN")
            logger.info(
                "[GRAPH_ROUTER] GRAPH_ENGINE subsystem is %s. "
                "Skipping graph traversal and silently falling back to Vector RAG.",
                current_status
            )
            # 그래프 로직 스킵하고 조용히(Silent Fallback) Vector RAG 결과 반환
            return vector_results
            
        # TODO: Phase 4-2 / 2단계: 하이브리드 탐색 알고리즘 결합 로직
        # FAISS 등 벡터 검색 결과의 Top-K 노드들을 그래프의 진입점(Seed Node)으로 설정하고,
        # GRAPH_MAX_TRAVERSAL_DEPTH를 넘지 않도록 무한 루프 방지용 Clamping 순회 로직 구현 예정.
        
        # 임시로 기존 vector_results 반환 (뼈대 단계)
        return vector_results

def run_hybrid_search(query: str, vector_results: List[Dict[str, Any]], **kwargs: Any) -> List[Dict[str, Any]]:
    """
    하이브리드 검색을 실행하는 헬퍼 함수
    """
    router = GraphHybridRouter()
    return router.route_query(query, vector_results, **kwargs)

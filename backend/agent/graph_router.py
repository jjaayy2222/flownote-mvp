# backend/agent/graph_router.py

"""
Phase 4-2: GraphRAG 하이브리드 라우터

책임:
  - 매 쿼리마다 HealthRegistry.is_ok(Subsystem.GRAPH_ENGINE)를 최우선 검사.
    False 반환 시 그래프 탐색을 스킵하고 즉시 Vector RAG로 Silent Fallback.
  - 벡터 검색 결과의 Top-K 노드를 Seed Node로 삼아 지식 그래프 BFS 탐색 수행.
  - GRAPH_MAX_TRAVERSAL_DEPTH 환경 변수를 [1, 5] 범위로 Clamping하여 무한 루프 방지.
  - 그래프 탐색 결과를 Vector RAG 결과에 결합하여 반환.

보안 원칙:
  - hashed_user_id 단위로 테넌트를 격리하여 타 사용자 그래프가 섞이지 않는다.
  - PII(user_id 원문)는 절대 이 모듈 어디에도 전달되지 않는다.
  - stateless_load 컨텍스트 매니저를 사용하여 조회 후 인메모리 데이터를 즉시 정리.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.core.health_registry import HealthRegistry
from backend.core.config_validator import Subsystem
from backend.core.config.graph import (
    MAX_TRAVERSAL_DEPTH_RANGE,
    DEFAULT_MAX_TRAVERSAL_DEPTH,
    ENV_MAX_TRAVERSAL_DEPTH,
)
from backend.graph.base import AbstractGraphRepository

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _clamp_depth(depth: int) -> int:
    """
    탐색 깊이를 [1, 5] 범위로 강제(Clamping).

    GRAPH_MAX_TRAVERSAL_DEPTH 환경 변수가 범위를 벗어나거나 파싱에 실패한 경우에도
    이 함수가 최후 방어선으로 작동하여 무한 루프를 예방한다.

    Args:
        depth: 적용 예정 탐색 깊이

    Returns:
        [1, 5] 범위로 보정된 탐색 깊이
    """
    min_depth = MAX_TRAVERSAL_DEPTH_RANGE.min
    max_depth = MAX_TRAVERSAL_DEPTH_RANGE.max
    clamped = max(min_depth, min(depth, max_depth))
    if clamped != depth:
        logger.warning(
            "[GRAPH_ROUTER] GRAPH_MAX_TRAVERSAL_DEPTH=%d is out of range [%d, %d]. "
            "Clamped to %d.",
            depth,
            min_depth,
            max_depth,
            clamped,
        )
    return clamped


def _load_traversal_depth() -> int:
    """
    환경 변수에서 GRAPH_MAX_TRAVERSAL_DEPTH를 읽어 Clamping 후 반환한다.

    GraphEngineConfig.from_env()를 재호출하지 않고 경량으로 처리하기 위해
    os.environ을 직접 참조하며, 파싱 실패 시 기본값을 사용한다.
    최종 Clamping은 _clamp_depth()에 위임하여 중복 로직을 방지한다.

    Returns:
        보정된 탐색 깊이 (int)
    """
    import os
    raw = os.environ.get(ENV_MAX_TRAVERSAL_DEPTH, "")
    if raw.strip():
        try:
            return _clamp_depth(int(raw.strip()))
        except ValueError:
            logger.warning(
                "[GRAPH_ROUTER] Cannot parse %s='%s' as int; "
                "falling back to default=%d.",
                ENV_MAX_TRAVERSAL_DEPTH,
                raw,
                DEFAULT_MAX_TRAVERSAL_DEPTH,
            )
    return _clamp_depth(DEFAULT_MAX_TRAVERSAL_DEPTH)


def _extract_seed_node_ids(vector_results: List[Dict[str, Any]]) -> List[str]:
    """
    vector_results에서 고유한 Seed Node ID 목록을 추출한다.

    각 결과 딕셔너리의 'id' 또는 'metadata.id', 'metadata.source' 필드를 우선순위
    순서로 탐색하여 Seed Node를 식별한다. 원래 스코어 순서(내림차순)를 보존하며
    중복을 제거한다.

    ID는 다음 우선순위로 추출되며, 문자열이 아닌 ID는 str()로 정규화된다.
    - result['id']
    - result['metadata']['id']
    - result['metadata']['source']

    비문자열 ID를 발견하면 경고 로그를 남기고, str() 변환에 실패하는 경우에만
    해당 항목을 건너뛴다.

    Args:
        vector_results: 벡터 검색 결과 리스트. 각 항목은
            {'content': ..., 'metadata': ..., 'score': ...} 형식.

    Returns:
        스코어 순서를 보존한 고유 Seed Node ID 문자열 리스트.
    """
    seed_node_ids: List[str] = []
    seen_ids: set[str] = set()
    coerced_count = 0

    for idx, result in enumerate(vector_results):
        node_id = None
        source_field = None

        # 1) result['id']
        if "id" in result and result["id"] is not None:
            node_id = result["id"]
            source_field = "id"
        else:
            metadata = result.get("metadata")
            if isinstance(metadata, dict):
                # 2) result['metadata']['id']
                if metadata.get("id") is not None:
                    node_id = metadata["id"]
                    source_field = "metadata.id"
                # 3) result['metadata']['source']
                elif metadata.get("source") is not None:
                    node_id = metadata["source"]
                    source_field = "metadata.source"

        if node_id is None:
            # No usable ID for this result; silently skip to preserve previous behavior.
            continue

        # Normalize non-string IDs and log for observability.
        if not isinstance(node_id, str):
            logger.debug(
                "[GRAPH_ROUTER] Non-string seed node id from %s at index %d: %r (type=%s); coercing to str.",
                source_field or "<unknown>",
                idx,
                node_id,
                type(node_id).__name__,
            )
            try:
                node_id_str = str(node_id)
                coerced_count += 1
            except Exception:
                logger.error(
                    "[GRAPH_ROUTER] Failed to coerce seed node id from %s at index %d to str; skipping.",
                    source_field or "<unknown>",
                    idx,
                    exc_info=True,
                )
                continue
        else:
            node_id_str = node_id

        # Skip empty strings after normalization
        if not node_id_str:
            continue

        if node_id_str not in seen_ids:
            seen_ids.add(node_id_str)
            seed_node_ids.append(node_id_str)

    if coerced_count > 0:
        logger.info(
            "[GRAPH_ROUTER] Coerced %d non-string seed node IDs to str.", coerced_count
        )

    return seed_node_ids


def _serialize_neighbor_node(
    node_id: str,
    attrs: Dict[str, Any],
    graph_score: float = 0.5,
) -> Dict[str, Any]:
    """
    그래프 이웃 노드를 RAG 결과 표준 포맷으로 직렬화한다.

    Args:
        node_id     : 이웃 노드 ID
        attrs       : get_node_attrs()로 조회한 노드 속성 딕셔너리
        graph_score : 그래프 탐색으로 발견된 노드의 기본 점수 (기본값: 0.5)

    Returns:
        {'content': str, 'metadata': dict, 'score': float} 형식의 딕셔너리
    """
    # content: 노드 속성에서 텍스트 필드를 우선 탐색
    content = (
        attrs.get("content")
        or attrs.get("text")
        or attrs.get("title")
        or node_id
    )
    return {
        "content": str(content),
        "metadata": {
            **{
                k: v
                for k, v in attrs.items()
                if k not in ("content", "text", "source", "id")
            },
            "id": node_id,
            "source": attrs.get("source", node_id),
        },
        "score": graph_score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GraphHybridRouter
# ─────────────────────────────────────────────────────────────────────────────

class GraphHybridRouter:
    """
    기존 벡터 검색(Vector RAG) 결과와 지식 그래프 탐색 결과를 결합하는 하이브리드 쿼리 라우터.

    DI(의존성 주입) 계약:
        - health_registry: 명시적 None 체크로 주입 여부를 판단한다. falsy한 유사
          인스턴스가 단락 평가(or)로 누락되는 버그를 원천 방지.
        - graph_repository: 선택적 주입. None이면 route_query 호출 시 그래프 탐색을
          스킵하지 않으나, hashed_user_id와 함께 전달해야 실제 탐색이 수행된다.

    테스트 격리:
        생성자 주입을 통해 Mock HealthRegistry / Mock Repository를 손쉽게 주입할 수 있다.
    """

    def __init__(
        self,
        health_registry: Optional[HealthRegistry] = None,
        graph_repository: Optional[AbstractGraphRepository] = None,
    ) -> None:
        # 명시적 None 체크 — falsy한 유효 인스턴스가 or 단락으로 버려지는 버그 방지
        if health_registry is None:
            self.health_registry = HealthRegistry.get_instance()
        else:
            self.health_registry = health_registry

        # graph_repository는 None도 유효 상태 (route_query에서 개별 처리)
        self.graph_repository: Optional[AbstractGraphRepository] = graph_repository

    def route_query(
        self,
        query: str,
        vector_results: List[Dict[str, Any]],
        hashed_user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        벡터 검색 결과(vector_results)를 입력받아 그래프 탐색과 결합하여 하이브리드 결과를 반환한다.

        동작 순서:
            1. HealthRegistry.is_ok(GRAPH_ENGINE) 체크 → False면 즉시 Silent Fallback.
            2. hashed_user_id 또는 graph_repository 없으면 그래프 탐색 스킵.
            3. vector_results에서 Seed Node ID 추출.
            4. GRAPH_MAX_TRAVERSAL_DEPTH Clamping 후 BFS 이웃 탐색.
            5. 이웃 노드를 RAG 포맷으로 직렬화하여 vector_results에 결합 반환.

        Args:
            query           : 사용자 쿼리 (로깅 목적, 현재 탐색 로직에는 미사용)
            vector_results  : 벡터 검색 결과 리스트
            hashed_user_id  : 테넌트 식별자 (SHA-256 hex, PII 미포함). None이면 탐색 스킵.

        Returns:
            vector_results + 그래프 이웃 노드 결과가 결합된 리스트.
            탐색 실패 또는 헬스 이상 시 원본 vector_results(또는 예외 발생 직전까지 수집된 부분 결과) 반환.
        """
        # ── 1단계: SSOT 상태 검사 (최우선 가드레일) ─────────────────────────
        if not self.health_registry.is_ok(Subsystem.GRAPH_ENGINE):
            summary = self.health_registry.get_summary()
            current_status = summary.get(Subsystem.GRAPH_ENGINE.value, "UNKNOWN")
            logger.warning(
                "[GRAPH_ROUTER] GRAPH_ENGINE subsystem is %s. "
                "Skipping graph traversal and silently falling back to Vector RAG.",
                current_status,
                extra={
                    "subsystem": Subsystem.GRAPH_ENGINE.value,
                    "status": current_status,
                },
            )
            return vector_results

        # ── 2단계: 탐색 가능 여부 사전 검사 ────────────────────────────────
        if not hashed_user_id or self.graph_repository is None:
            logger.debug(
                "[GRAPH_ROUTER] Graph traversal skipped: "
                "hashed_user_id=%s, repository_available=%s. "
                "Returning vector_results as-is.",
                "provided" if hashed_user_id else "missing",
                self.graph_repository is not None,
            )
            return vector_results

        # ── 3단계: Seed Node 추출 ────────────────────────────────────────────
        seed_ids = _extract_seed_node_ids(vector_results)

        if not seed_ids:
            logger.debug(
                "[GRAPH_ROUTER] No valid seed node IDs found in vector_results. "
                "Returning vector_results as-is."
            )
            return vector_results

        # ── 4단계: GRAPH_MAX_TRAVERSAL_DEPTH Clamping ────────────────────────
        max_depth = _load_traversal_depth()

        # ── 5단계: BFS 탐색 및 결과 수집 ─────────────────────────────────────
        return self._traverse_and_enrich(
            seed_ids, vector_results, hashed_user_id, max_depth
        )

    def _traverse_and_enrich(
        self,
        seed_ids: List[str],
        vector_results: List[Dict[str, Any]],
        hashed_user_id: str,
        max_depth: int,
    ) -> List[Dict[str, Any]]:
        graph_enriched: List[Dict[str, Any]] = list(vector_results)
        visited_neighbor_ids: set[str] = set(seed_ids)

        try:
            assert self.graph_repository is not None  # guarded earlier
            with self.graph_repository.stateless_load(hashed_user_id) as repo:
                for seed_id in seed_ids:
                    neighbors = repo.neighbors(
                        hashed_user_id,
                        seed_id,
                        max_depth=max_depth,
                    )
                    for neighbor_id in neighbors:
                        if neighbor_id in visited_neighbor_ids:
                            continue
                        visited_neighbor_ids.add(neighbor_id)

                        attrs = repo.get_node_attrs(hashed_user_id, neighbor_id) or {}
                        graph_enriched.append(
                            _serialize_neighbor_node(neighbor_id, attrs)
                        )
        except Exception:
            logger.exception(
                "[GRAPH_ROUTER] Unexpected error during graph traversal. "
                "Returning partially enriched results (or original vector_results)."
            )
            return graph_enriched

        logger.debug(
            "[GRAPH_ROUTER] Graph traversal complete. "
            "seeds=%d, neighbors_added=%d, total_results=%d, depth=%d.",
            len(seed_ids),
            len(graph_enriched) - len(vector_results),
            len(graph_enriched),
            max_depth,
        )
        return graph_enriched


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼 함수
# ─────────────────────────────────────────────────────────────────────────────

def run_hybrid_search(
    query: str,
    vector_results: List[Dict[str, Any]],
    router: Optional[GraphHybridRouter] = None,
    hashed_user_id: Optional[str] = None,
    graph_repository: Optional[AbstractGraphRepository] = None,
) -> List[Dict[str, Any]]:
    """
    하이브리드 검색을 실행하는 헬퍼 함수.

    Args:
        query           : 사용자 쿼리
        vector_results  : 벡터 검색 결과 리스트
        router          : GraphHybridRouter 인스턴스 (None이면 기본 생성).
                          테스트 또는 IoC 컨테이너에서 주입할 수 있다.
        hashed_user_id  : 테넌트 식별자 (PII 미포함). None이면 그래프 탐색 스킵.
        graph_repository: Repository 인스턴스 (None이면 router 생성자 주입 사용).

    Returns:
        vector_results + 그래프 탐색 결과가 결합된 리스트.
    """
    if router is not None and graph_repository is not None:
        logger.warning(
            "[GRAPH_ROUTER] Custom router provided along with graph_repository to run_hybrid_search. "
            "The graph_repository argument will be ignored."
        )

    if router is None:
        router = GraphHybridRouter(graph_repository=graph_repository)
    return router.route_query(
        query,
        vector_results,
        hashed_user_id=hashed_user_id,
    )

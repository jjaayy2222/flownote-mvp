# tests/unit/test_graph_router.py

"""
Phase 4-2 Step 2: GraphHybridRouter 단위 테스트
================================================

테스트 범위:
  - Silent Fallback: GRAPH_ENGINE이 DEGRADED/비정상 시 vector_results 원본 반환.
  - Seed Node 파싱: vector_results에서 id/metadata 필드 정확히 추출.
  - Clamping 경계: GRAPH_MAX_TRAVERSAL_DEPTH [1, 5] 강제.
  - BFS 탐색: 체인/다이아몬드/사이클 그래프에서 무한 루프 없이 이웃 수집.
  - stateless_load 라이프사이클: 조회 후 인메모리 자원 해제 검증.
  - 반환 결과 스키마: content/metadata/score 필드 포함 여부.
  - 의존성 주입(DI): 생성자 및 route_query 인자로 repository 주입 가능.
  - 예외 격리: 탐색 중 예외 발생 시 vector_results 원본으로 Silent Fallback.

보안 원칙:
  - 테스트 더미 hashed_user_id는 실제 PII를 포함하지 않는 64자 hex 고정값 사용.
  - storage_base_path는 tmp_path(pytest fixture)만 사용.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, call, patch

import pytest

from backend.agent.graph_router import (
    GraphHybridRouter,
    _clamp_depth,
    _extract_seed_node_ids,
    _load_traversal_depth,
    _serialize_neighbor_node,
    run_hybrid_search,
)
from backend.core.config.graph import (
    DEFAULT_MAX_TRAVERSAL_DEPTH,
    ENV_MAX_TRAVERSAL_DEPTH,
    MAX_TRAVERSAL_DEPTH_RANGE,
)
from backend.core.config_validator import Subsystem
from backend.graph.networkx_repository import NetworkXGraphRepository

# ─────────────────────────────────────────────────────────────────────────────
# 테스트 더미 상수 — PII 미포함, 64자 hex
# ─────────────────────────────────────────────────────────────────────────────

_DUMMY_HASH = "a" * 64
_DUMMY_HASH_B = "b" * 64  # 테넌트 격리 검증용

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def healthy_registry() -> MagicMock:
    """GRAPH_ENGINE이 정상(HEALTHY) 상태인 Mock HealthRegistry."""
    registry = MagicMock()
    registry.is_ok.return_value = True
    return registry


@pytest.fixture()
def degraded_registry() -> MagicMock:
    """GRAPH_ENGINE이 DEGRADED 상태인 Mock HealthRegistry."""
    registry = MagicMock()
    registry.is_ok.return_value = False
    registry.get_summary.return_value = {Subsystem.GRAPH_ENGINE.value: "DEGRADED"}
    return registry


@pytest.fixture()
def storage_path(tmp_path: Path) -> str:
    """각 테스트마다 격리된 임시 storage_base_path."""
    return str(tmp_path)


@pytest.fixture()
def repo(storage_path: str) -> NetworkXGraphRepository:
    """테스트용 NetworkXGraphRepository 인스턴스."""
    return NetworkXGraphRepository(storage_base_path=storage_path)


@pytest.fixture()
def simple_vector_results() -> List[Dict[str, Any]]:
    """단순 벡터 검색 결과 픽스처 (id 필드 포함)."""
    return [
        {"id": "note-001", "content": "Python basics", "metadata": {}, "score": 0.9},
        {"id": "note-002", "content": "Machine learning", "metadata": {}, "score": 0.8},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# _clamp_depth 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────


class TestClampDepth:
    def test_value_within_range_is_unchanged(self) -> None:
        assert _clamp_depth(3) == 3

    def test_min_boundary_is_preserved(self) -> None:
        assert _clamp_depth(MAX_TRAVERSAL_DEPTH_RANGE.min) == MAX_TRAVERSAL_DEPTH_RANGE.min

    def test_max_boundary_is_preserved(self) -> None:
        assert _clamp_depth(MAX_TRAVERSAL_DEPTH_RANGE.max) == MAX_TRAVERSAL_DEPTH_RANGE.max

    def test_below_min_is_clamped_to_min(self) -> None:
        assert _clamp_depth(0) == MAX_TRAVERSAL_DEPTH_RANGE.min
        assert _clamp_depth(-5) == MAX_TRAVERSAL_DEPTH_RANGE.min

    def test_above_max_is_clamped_to_max(self) -> None:
        assert _clamp_depth(10) == MAX_TRAVERSAL_DEPTH_RANGE.max
        assert _clamp_depth(999) == MAX_TRAVERSAL_DEPTH_RANGE.max


# ─────────────────────────────────────────────────────────────────────────────
# _load_traversal_depth 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────


class TestLoadTraversalDepth:
    def test_returns_default_when_env_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_MAX_TRAVERSAL_DEPTH, raising=False)
        assert _load_traversal_depth() == _clamp_depth(DEFAULT_MAX_TRAVERSAL_DEPTH)

    def test_reads_valid_env_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "2")
        assert _load_traversal_depth() == 2

    def test_clamps_env_value_above_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "99")
        assert _load_traversal_depth() == MAX_TRAVERSAL_DEPTH_RANGE.max

    def test_clamps_env_value_below_min(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "0")
        assert _load_traversal_depth() == MAX_TRAVERSAL_DEPTH_RANGE.min

    def test_returns_default_on_non_integer_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "not_a_number")
        assert _load_traversal_depth() == _clamp_depth(DEFAULT_MAX_TRAVERSAL_DEPTH)


# ─────────────────────────────────────────────────────────────────────────────
# _extract_seed_node_ids 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractSeedNodeIds:
    def test_extracts_top_level_id_field(self) -> None:
        results = [
            {"id": "note-A", "content": "...", "score": 0.9},
            {"id": "note-B", "content": "...", "score": 0.8},
        ]
        assert _extract_seed_node_ids(results) == ["note-A", "note-B"]

    def test_falls_back_to_metadata_id(self) -> None:
        results = [
            {"content": "...", "metadata": {"id": "note-C"}, "score": 0.7},
        ]
        assert _extract_seed_node_ids(results) == ["note-C"]

    def test_falls_back_to_metadata_source(self) -> None:
        results = [
            {"content": "...", "metadata": {"source": "note-D"}, "score": 0.6},
        ]
        assert _extract_seed_node_ids(results) == ["note-D"]

    def test_top_level_id_takes_priority_over_metadata(self) -> None:
        results = [
            {"id": "note-E", "metadata": {"id": "note-F", "source": "note-G"}, "score": 0.5},
        ]
        assert _extract_seed_node_ids(results) == ["note-E"]

    def test_deduplicates_ids(self) -> None:
        results = [
            {"id": "note-A", "content": "...", "score": 0.9},
            {"id": "note-A", "content": "...", "score": 0.85},
            {"id": "note-B", "content": "...", "score": 0.8},
        ]
        ids = _extract_seed_node_ids(results)
        assert ids == ["note-A", "note-B"]

    def test_skips_results_without_id(self) -> None:
        results = [
            {"content": "no id here", "metadata": {}, "score": 0.5},
        ]
        assert _extract_seed_node_ids(results) == []

    def test_preserves_score_order(self) -> None:
        results = [
            {"id": "note-Z", "content": "...", "score": 0.95},
            {"id": "note-A", "content": "...", "score": 0.7},
        ]
        assert _extract_seed_node_ids(results) == ["note-Z", "note-A"]

    def test_empty_input_returns_empty_list(self) -> None:
        assert _extract_seed_node_ids([]) == []


# ─────────────────────────────────────────────────────────────────────────────
# _serialize_neighbor_node 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────


class TestSerializeNeighborNode:
    def test_returns_required_schema_fields(self) -> None:
        result = _serialize_neighbor_node("node-X", {"title": "Test Note"})
        assert "content" in result
        assert "metadata" in result
        assert "score" in result

    def test_uses_content_field_if_available(self) -> None:
        result = _serialize_neighbor_node("node-X", {"content": "Hello World"})
        assert result["content"] == "Hello World"

    def test_falls_back_to_text_then_title(self) -> None:
        result_text = _serialize_neighbor_node("node-X", {"text": "Via Text"})
        assert result_text["content"] == "Via Text"

        result_title = _serialize_neighbor_node("node-X", {"title": "Via Title"})
        assert result_title["content"] == "Via Title"

    def test_falls_back_to_node_id_when_no_text(self) -> None:
        result = _serialize_neighbor_node("node-X", {})
        assert result["content"] == "node-X"

    def test_metadata_contains_id(self) -> None:
        result = _serialize_neighbor_node("node-X", {"title": "Test"})
        assert result["metadata"]["id"] == "node-X"

    def test_custom_score_is_applied(self) -> None:
        result = _serialize_neighbor_node("node-X", {}, graph_score=0.75)
        assert result["score"] == 0.75


# ─────────────────────────────────────────────────────────────────────────────
# GraphHybridRouter.route_query 동작 테스트
# ─────────────────────────────────────────────────────────────────────────────


class TestRouteQuerySilentFallback:
    """GRAPH_ENGINE 비정상 시 Silent Fallback 검증."""

    def test_returns_vector_results_when_degraded(
        self,
        degraded_registry: MagicMock,
        simple_vector_results: List[Dict[str, Any]],
    ) -> None:
        router = GraphHybridRouter(health_registry=degraded_registry)
        result = router.route_query("query", simple_vector_results)
        assert result is simple_vector_results

    def test_does_not_raise_when_degraded(
        self,
        degraded_registry: MagicMock,
        simple_vector_results: List[Dict[str, Any]],
    ) -> None:
        router = GraphHybridRouter(health_registry=degraded_registry)
        # 예외 없이 정상 반환되어야 함
        router.route_query("query", simple_vector_results)

    def test_is_ok_called_with_graph_engine_subsystem(
        self,
        degraded_registry: MagicMock,
        simple_vector_results: List[Dict[str, Any]],
    ) -> None:
        router = GraphHybridRouter(health_registry=degraded_registry)
        router.route_query("query", simple_vector_results)
        degraded_registry.is_ok.assert_called_once_with(Subsystem.GRAPH_ENGINE)


class TestRouteQuerySkipConditions:
    """hashed_user_id 또는 repository 누락 시 탐색 스킵 검증."""

    def test_skips_traversal_without_hashed_user_id(
        self,
        healthy_registry: MagicMock,
        simple_vector_results: List[Dict[str, Any]],
        repo: NetworkXGraphRepository,
    ) -> None:
        router = GraphHybridRouter(health_registry=healthy_registry, graph_repository=repo)
        result = router.route_query("query", simple_vector_results, hashed_user_id=None)
        assert result is simple_vector_results

    def test_skips_traversal_without_repository(
        self,
        healthy_registry: MagicMock,
        simple_vector_results: List[Dict[str, Any]],
    ) -> None:
        router = GraphHybridRouter(health_registry=healthy_registry, graph_repository=None)
        result = router.route_query(
            "query",
            simple_vector_results,
            hashed_user_id=_DUMMY_HASH,
            graph_repository=None,
        )
        assert result is simple_vector_results

    def test_skips_traversal_when_seed_nodes_empty(
        self,
        healthy_registry: MagicMock,
        repo: NetworkXGraphRepository,
    ) -> None:
        # id 필드 없는 vector_results → Seed Node 없음 → 탐색 스킵
        no_id_results = [{"content": "text", "score": 0.5}]
        router = GraphHybridRouter(health_registry=healthy_registry, graph_repository=repo)
        result = router.route_query(
            "query",
            no_id_results,
            hashed_user_id=_DUMMY_HASH,
        )
        assert result is no_id_results


# ─────────────────────────────────────────────────────────────────────────────
# BFS 탐색 그래프 구조 테스트
# ─────────────────────────────────────────────────────────────────────────────


class TestRouteQueryBFSTraversal:
    """다양한 그래프 구조에서 BFS 탐색 정확도 및 안전성 검증."""

    def _make_vector_results(self, node_id: str) -> List[Dict[str, Any]]:
        return [{"id": node_id, "content": "Seed", "metadata": {}, "score": 0.9}]

    def test_chain_graph_traversal(
        self,
        healthy_registry: MagicMock,
        repo: NetworkXGraphRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """체인 A → B → C 그래프에서 depth=2 탐색 시 B, C 모두 수집."""
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "2")
        repo.add_node(_DUMMY_HASH, "A", title="Node A")
        repo.add_node(_DUMMY_HASH, "B", title="Node B")
        repo.add_node(_DUMMY_HASH, "C", title="Node C")
        repo.add_edge(_DUMMY_HASH, "A", "B")
        repo.add_edge(_DUMMY_HASH, "B", "C")
        repo.persist(_DUMMY_HASH)

        router = GraphHybridRouter(health_registry=healthy_registry)
        results = router.route_query(
            "query",
            self._make_vector_results("A"),
            hashed_user_id=_DUMMY_HASH,
            graph_repository=repo,
        )
        result_ids = {r.get("metadata", {}).get("id") or r.get("id") for r in results}
        assert "B" in result_ids
        assert "C" in result_ids

    def test_diamond_graph_no_duplicate(
        self,
        healthy_registry: MagicMock,
        repo: NetworkXGraphRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """다이아몬드 A→B, A→C, B→D, C→D에서 D가 중복 없이 1회만 수집."""
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "3")
        for nid in ["A", "B", "C", "D"]:
            repo.add_node(_DUMMY_HASH, nid, title=f"Node {nid}")
        repo.add_edge(_DUMMY_HASH, "A", "B")
        repo.add_edge(_DUMMY_HASH, "A", "C")
        repo.add_edge(_DUMMY_HASH, "B", "D")
        repo.add_edge(_DUMMY_HASH, "C", "D")
        repo.persist(_DUMMY_HASH)

        router = GraphHybridRouter(health_registry=healthy_registry)
        results = router.route_query(
            "query",
            self._make_vector_results("A"),
            hashed_user_id=_DUMMY_HASH,
            graph_repository=repo,
        )
        neighbor_ids = [
            r.get("metadata", {}).get("id")
            for r in results
            if r.get("metadata", {}).get("id") != "A"
        ]
        assert neighbor_ids.count("D") == 1, "D should appear exactly once (no duplicates)"

    def test_cycle_graph_no_infinite_loop(
        self,
        healthy_registry: MagicMock,
        repo: NetworkXGraphRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """사이클 A→B→C→A 그래프에서 무한 루프 없이 탐색 완료."""
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "5")
        for nid in ["A", "B", "C"]:
            repo.add_node(_DUMMY_HASH, nid, title=f"Node {nid}")
        repo.add_edge(_DUMMY_HASH, "A", "B")
        repo.add_edge(_DUMMY_HASH, "B", "C")
        repo.add_edge(_DUMMY_HASH, "C", "A")
        repo.persist(_DUMMY_HASH)

        router = GraphHybridRouter(health_registry=healthy_registry)
        # 무한 루프라면 여기서 타임아웃 발생 — 통과하면 안전함
        results = router.route_query(
            "query",
            self._make_vector_results("A"),
            hashed_user_id=_DUMMY_HASH,
            graph_repository=repo,
        )
        assert len(results) > 0

    def test_isolated_node_returns_only_vector_results(
        self,
        healthy_registry: MagicMock,
        repo: NetworkXGraphRepository,
    ) -> None:
        """고립 노드(이웃 없음) Seed의 경우 vector_results만 반환."""
        repo.add_node(_DUMMY_HASH, "isolated", title="Lonely Node")
        repo.persist(_DUMMY_HASH)

        router = GraphHybridRouter(health_registry=healthy_registry)
        vector_in = self._make_vector_results("isolated")
        results = router.route_query(
            "query",
            vector_in,
            hashed_user_id=_DUMMY_HASH,
            graph_repository=repo,
        )
        assert results == vector_in

    def test_result_items_have_required_schema(
        self,
        healthy_registry: MagicMock,
        repo: NetworkXGraphRepository,
    ) -> None:
        """반환된 그래프 이웃 노드 결과가 content/metadata/score 스키마를 갖는지 검증."""
        repo.add_node(_DUMMY_HASH, "A", title="Node A", content="A content")
        repo.add_node(_DUMMY_HASH, "B", title="Node B", content="B content")
        repo.add_edge(_DUMMY_HASH, "A", "B")
        repo.persist(_DUMMY_HASH)

        router = GraphHybridRouter(health_registry=healthy_registry)
        results = router.route_query(
            "query",
            self._make_vector_results("A"),
            hashed_user_id=_DUMMY_HASH,
            graph_repository=repo,
        )
        graph_nodes = [r for r in results if r.get("metadata", {}).get("id") == "B"]
        assert len(graph_nodes) == 1
        node = graph_nodes[0]
        assert "content" in node
        assert "metadata" in node
        assert "score" in node
        assert isinstance(node["score"], float)


# ─────────────────────────────────────────────────────────────────────────────
# stateless_load 라이프사이클 검증
# ─────────────────────────────────────────────────────────────────────────────


class TestStatelessLoadLifecycle:
    def test_graph_cleared_after_traversal(
        self,
        healthy_registry: MagicMock,
        repo: NetworkXGraphRepository,
    ) -> None:
        """stateless_load 컨텍스트 종료 후 인메모리 그래프가 비어 있어야 한다."""
        repo.add_node(_DUMMY_HASH, "A", title="Node A")
        repo.add_node(_DUMMY_HASH, "B", title="Node B")
        repo.add_edge(_DUMMY_HASH, "A", "B")
        repo.persist(_DUMMY_HASH)

        router = GraphHybridRouter(health_registry=healthy_registry)
        vector_in = [{"id": "A", "content": "Seed", "metadata": {}, "score": 0.9}]
        router.route_query(
            "query",
            vector_in,
            hashed_user_id=_DUMMY_HASH,
            graph_repository=repo,
        )
        # 탐색 완료 후 node_count()는 0이어야 한다 (clear 호출됨)
        assert repo.node_count(_DUMMY_HASH) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 예외 격리 (Exception Isolation)
# ─────────────────────────────────────────────────────────────────────────────


class TestExceptionIsolation:
    def test_exception_in_traversal_falls_back_to_vector_results(
        self,
        healthy_registry: MagicMock,
        simple_vector_results: List[Dict[str, Any]],
    ) -> None:
        """탐색 중 예외 발생 시 vector_results 원본 반환, 예외 전파 없음."""
        broken_repo = MagicMock()
        # stateless_load를 컨텍스트 매니저처럼 동작하되 내부에서 예외 발생
        broken_repo.stateless_load.side_effect = RuntimeError("Simulated IO failure")

        router = GraphHybridRouter(health_registry=healthy_registry)
        result = router.route_query(
            "query",
            simple_vector_results,
            hashed_user_id=_DUMMY_HASH,
            graph_repository=broken_repo,
        )
        assert result is simple_vector_results


# ─────────────────────────────────────────────────────────────────────────────
# 의존성 주입 (DI) 검증
# ─────────────────────────────────────────────────────────────────────────────


class TestDependencyInjection:
    def test_constructor_injected_registry_is_used(
        self,
        degraded_registry: MagicMock,
        simple_vector_results: List[Dict[str, Any]],
    ) -> None:
        """생성자로 주입한 registry가 실제로 사용되는지 검증."""
        router = GraphHybridRouter(health_registry=degraded_registry)
        router.route_query("q", simple_vector_results)
        degraded_registry.is_ok.assert_called()

    def test_route_query_repo_overrides_constructor_repo(
        self,
        healthy_registry: MagicMock,
        repo: NetworkXGraphRepository,
    ) -> None:
        """route_query의 graph_repository 인자가 생성자 주입보다 우선한다."""
        fallback_repo = MagicMock()
        fallback_repo.stateless_load.return_value.__enter__ = MagicMock(return_value=fallback_repo)
        fallback_repo.stateless_load.return_value.__exit__ = MagicMock(return_value=False)
        fallback_repo.neighbors.return_value = []

        router = GraphHybridRouter(
            health_registry=healthy_registry,
            graph_repository=fallback_repo,  # 생성자 주입
        )
        # route_query에서 다른 repo를 전달하면 이쪽이 사용되어야 함
        # (repo는 실제 NetworkXGraphRepository — 데이터 없어 이웃도 없음)
        vector_in = [{"id": "A", "content": "seed", "metadata": {}, "score": 0.9}]
        router.route_query(
            "q",
            vector_in,
            hashed_user_id=_DUMMY_HASH,
            graph_repository=repo,  # 인자 우선
        )
        # fallback_repo.stateless_load은 호출되지 않아야 함
        fallback_repo.stateless_load.assert_not_called()

    def test_none_registry_uses_global_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """health_registry=None이면 HealthRegistry.get_instance()를 호출한다."""
        mock_instance = MagicMock()
        mock_instance.is_ok.return_value = False
        mock_instance.get_summary.return_value = {}

        with patch(
            "backend.agent.graph_router.HealthRegistry.get_instance",
            return_value=mock_instance,
        ):
            router = GraphHybridRouter(health_registry=None)
            router.route_query("q", [])
            mock_instance.is_ok.assert_called_once_with(Subsystem.GRAPH_ENGINE)


# ─────────────────────────────────────────────────────────────────────────────
# run_hybrid_search 헬퍼 함수 테스트
# ─────────────────────────────────────────────────────────────────────────────


class TestRunHybridSearch:
    def test_creates_default_router_when_none(
        self,
        degraded_registry: MagicMock,
        simple_vector_results: List[Dict[str, Any]],
    ) -> None:
        """router=None이면 내부에서 GraphHybridRouter()를 생성한다."""
        # 글로벌 싱글톤을 degraded로 교체하여 실제 router 생성 경로 검증
        with patch(
            "backend.agent.graph_router.HealthRegistry.get_instance",
            return_value=degraded_registry,
        ):
            result = run_hybrid_search("q", simple_vector_results, router=None)
        assert result == simple_vector_results

    def test_uses_provided_router(
        self,
        simple_vector_results: List[Dict[str, Any]],
    ) -> None:
        """router가 제공되면 해당 router의 route_query를 사용한다."""
        mock_router = MagicMock()
        mock_router.route_query.return_value = simple_vector_results

        run_hybrid_search("q", simple_vector_results, router=mock_router)
        mock_router.route_query.assert_called_once()

    def test_passes_hashed_user_id_and_repo_to_route_query(
        self,
        simple_vector_results: List[Dict[str, Any]],
        repo: NetworkXGraphRepository,
    ) -> None:
        """hashed_user_id와 graph_repository가 route_query에 전달된다."""
        mock_router = MagicMock()
        mock_router.route_query.return_value = simple_vector_results

        run_hybrid_search(
            "q",
            simple_vector_results,
            router=mock_router,
            hashed_user_id=_DUMMY_HASH,
            graph_repository=repo,
        )
        call_kwargs = mock_router.route_query.call_args
        assert call_kwargs.kwargs.get("hashed_user_id") == _DUMMY_HASH
        assert call_kwargs.kwargs.get("graph_repository") is repo


# ─────────────────────────────────────────────────────────────────────────────
# 테넌트 격리 검증
# ─────────────────────────────────────────────────────────────────────────────


class TestTenantIsolation:
    def test_user_a_graph_does_not_leak_to_user_b(
        self,
        healthy_registry: MagicMock,
        repo: NetworkXGraphRepository,
    ) -> None:
        """사용자 A의 그래프 이웃이 사용자 B 조회에서 나타나지 않는다."""
        # 사용자 A: A → B 엣지
        repo.add_node(_DUMMY_HASH, "A", title="User A Node A")
        repo.add_node(_DUMMY_HASH, "B", title="User A Node B")
        repo.add_edge(_DUMMY_HASH, "A", "B")
        repo.persist(_DUMMY_HASH)

        # 사용자 B: 그래프 없음 (빈 그래프)
        router = GraphHybridRouter(health_registry=healthy_registry)
        vector_in_b = [{"id": "A", "content": "B's query", "metadata": {}, "score": 0.9}]
        result_b = router.route_query(
            "query",
            vector_in_b,
            hashed_user_id=_DUMMY_HASH_B,  # 사용자 B
            graph_repository=repo,
        )
        # 사용자 B의 결과에 사용자 A의 "B" 노드가 포함되어선 안 됨
        neighbor_ids = [
            r.get("metadata", {}).get("id")
            for r in result_b
            if r.get("metadata", {}).get("id") not in (None, "A")
        ]
        assert "B" not in neighbor_ids

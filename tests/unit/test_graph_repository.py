# tests/unit/test_graph_repository.py

"""
Phase 4-1: NetworkXGraphRepository 단위 테스트
=================================================

테스트 범위:
  - 경로 빌더(build_graph_path) 동작 및 엣지케이스
  - 노드/엣지 CRUD (멱등성, Silent no-op)
  - BFS 탐색(neighbors) — max_depth 경계
  - node_count / iter_nodes 통계
  - persist / load 원자적 쓰기 및 복원
  - 테넌트 격리 — 두 사용자 그래프가 서로에게 영향 없음
  - AbstractGraphRepository 계약 충족 확인

보안 원칙:
  - 테스트 더미 hashed_user_id는 실제 PII를 포함하지 않는 64자 hex 고정값 사용.
  - storage_base_path는 tmp_path(pytest fixture)만 사용 — 실제 파일시스템 오염 방지.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import networkx as nx
import pytest

from backend.graph.base import AbstractGraphRepository
from backend.graph.networkx_repository import NetworkXGraphRepository
from backend.graph.path_utils import build_graph_path

# ─────────────────────────────────────────────────────────────────────────────
# 테스트 더미 상수 — PII 미포함, 64자 hex
# ─────────────────────────────────────────────────────────────────────────────

_DUMMY_HASH_A = "a" * 64  # 사용자 A
_DUMMY_HASH_B = "b" * 64  # 사용자 B (테넌트 격리 검증용)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def storage_path(tmp_path: Path) -> str:
    """각 테스트마다 격리된 임시 storage_base_path를 반환한다."""
    return str(tmp_path)


@pytest.fixture()
def repo(storage_path: str) -> NetworkXGraphRepository:
    """테스트용 NetworkXGraphRepository 인스턴스."""
    return NetworkXGraphRepository(storage_base_path=storage_path)


# ─────────────────────────────────────────────────────────────────────────────
# build_graph_path 단위 테스트
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildGraphPath:
    def test_returns_path_with_correct_subdir_and_extension(
        self, storage_path: str
    ) -> None:
        path = build_graph_path(_DUMMY_HASH_A, storage_path)
        assert path.suffix == ".graphml"
        assert "graph_data" in str(path)
        assert _DUMMY_HASH_A in path.name

    def test_deterministic_for_same_inputs(self, storage_path: str) -> None:
        path1 = build_graph_path(_DUMMY_HASH_A, storage_path)
        path2 = build_graph_path(_DUMMY_HASH_A, storage_path)
        assert path1 == path2

    def test_different_hashes_yield_different_paths(self, storage_path: str) -> None:
        path_a = build_graph_path(_DUMMY_HASH_A, storage_path)
        path_b = build_graph_path(_DUMMY_HASH_B, storage_path)
        assert path_a != path_b

    def test_raises_on_empty_hashed_user_id(self, storage_path: str) -> None:
        with pytest.raises(ValueError, match="hashed_user_id"):
            build_graph_path("", storage_path)

    def test_raises_on_empty_storage_base_path(self) -> None:
        with pytest.raises(ValueError, match="storage_base_path"):
            build_graph_path(_DUMMY_HASH_A, "")


# ─────────────────────────────────────────────────────────────────────────────
# NetworkXGraphRepository 초기화
# ─────────────────────────────────────────────────────────────────────────────


class TestNetworkXRepositoryInit:
    def test_raises_on_empty_storage_base_path(self) -> None:
        with pytest.raises(ValueError, match="storage_base_path"):
            NetworkXGraphRepository(storage_base_path="")

    def test_implements_abstract_interface(self, repo: NetworkXGraphRepository) -> None:
        """ABC 계약 충족 — 인스턴스화 성공 자체가 증명."""
        assert isinstance(repo, AbstractGraphRepository)


# ─────────────────────────────────────────────────────────────────────────────
# 노드 CRUD
# ─────────────────────────────────────────────────────────────────────────────


class TestNodeCRUD:
    def test_add_and_has_node(self, repo: NetworkXGraphRepository) -> None:
        repo.add_node(_DUMMY_HASH_A, "node-1", title="Note A", node_type="note")
        assert repo.has_node(_DUMMY_HASH_A, "node-1") is True

    def test_has_node_returns_false_for_absent(
        self, repo: NetworkXGraphRepository
    ) -> None:
        assert repo.has_node(_DUMMY_HASH_A, "nonexistent") is False

    def test_add_node_is_idempotent_and_updates_attrs(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "node-1", title="Old")
        repo.add_node(_DUMMY_HASH_A, "node-1", title="New")
        attrs = repo.get_node_attrs(_DUMMY_HASH_A, "node-1")
        assert attrs is not None
        assert attrs["title"] == "New"

    def test_get_node_attrs_returns_none_for_absent(
        self, repo: NetworkXGraphRepository
    ) -> None:
        assert repo.get_node_attrs(_DUMMY_HASH_A, "ghost") is None

    def test_get_node_attrs_returns_defensive_copy(
        self, repo: NetworkXGraphRepository
    ) -> None:
        """반환된 dict 변경이 내부 상태에 영향을 주지 않아야 한다."""
        repo.add_node(_DUMMY_HASH_A, "node-1", title="Original")
        attrs = repo.get_node_attrs(_DUMMY_HASH_A, "node-1")
        assert attrs is not None
        attrs["title"] = "Mutated"
        attrs_again = repo.get_node_attrs(_DUMMY_HASH_A, "node-1")
        assert attrs_again is not None
        assert attrs_again["title"] == "Original"

    def test_remove_node_removes_node_and_edges(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "node-1")
        repo.add_node(_DUMMY_HASH_A, "node-2")
        repo.add_edge(_DUMMY_HASH_A, "node-1", "node-2")
        repo.remove_node(_DUMMY_HASH_A, "node-1")
        assert repo.has_node(_DUMMY_HASH_A, "node-1") is False
        assert repo.has_edge(_DUMMY_HASH_A, "node-1", "node-2") is False

    def test_remove_node_silent_noop_for_absent(
        self, repo: NetworkXGraphRepository
    ) -> None:
        """존재하지 않는 노드 제거 시 예외 없이 무시한다."""
        repo.remove_node(_DUMMY_HASH_A, "ghost")  # Must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 엣지 CRUD
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCRUD:
    def test_add_and_has_edge(self, repo: NetworkXGraphRepository) -> None:
        repo.add_node(_DUMMY_HASH_A, "src")
        repo.add_node(_DUMMY_HASH_A, "tgt")
        repo.add_edge(_DUMMY_HASH_A, "src", "tgt", weight=1.0, edge_type="explicit")
        assert repo.has_edge(_DUMMY_HASH_A, "src", "tgt") is True

    def test_has_edge_returns_false_for_absent(
        self, repo: NetworkXGraphRepository
    ) -> None:
        assert repo.has_edge(_DUMMY_HASH_A, "x", "y") is False

    def test_add_edge_is_idempotent_and_updates_attrs(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "src")
        repo.add_node(_DUMMY_HASH_A, "tgt")

        # First add with initial attributes
        repo.add_edge(_DUMMY_HASH_A, "src", "tgt", weight=0.5)

        # Second add should be idempotent for existence, but update attributes
        repo.add_edge(_DUMMY_HASH_A, "src", "tgt", weight=0.9)
        assert repo.has_edge(_DUMMY_HASH_A, "src", "tgt") is True

        # Attribute should reflect the most recent call
        attrs = repo.get_edge_attrs(_DUMMY_HASH_A, "src", "tgt")
        assert attrs is not None
        assert attrs["weight"] == 0.9

    def test_remove_edge_silent_noop_for_absent(
        self, repo: NetworkXGraphRepository
    ) -> None:
        """존재하지 않는 엣지 제거 시 예외 없이 무시한다."""
        repo.remove_edge(_DUMMY_HASH_A, "ghost-src", "ghost-tgt")  # Must not raise

    def test_edge_is_directed(self, repo: NetworkXGraphRepository) -> None:
        """DiGraph 방향성 확인 — A→B는 B→A와 다르다."""
        repo.add_edge(_DUMMY_HASH_A, "a", "b")
        assert repo.has_edge(_DUMMY_HASH_A, "a", "b") is True
        assert repo.has_edge(_DUMMY_HASH_A, "b", "a") is False


# ─────────────────────────────────────────────────────────────────────────────
# BFS 탐색 (neighbors)
# ─────────────────────────────────────────────────────────────────────────────


class TestNeighbors:
    def _add_abcd_nodes(self, repo: NetworkXGraphRepository) -> None:
        """A, B, C, D 노드를 추가한다."""
        for node in ("A", "B", "C", "D"):
            repo.add_node(_DUMMY_HASH_A, node)

    def _build_chain(self, repo: NetworkXGraphRepository) -> None:
        """A → B → C → D 체인 그래프."""
        self._add_abcd_nodes(repo)
        repo.add_edge(_DUMMY_HASH_A, "A", "B")
        repo.add_edge(_DUMMY_HASH_A, "B", "C")
        repo.add_edge(_DUMMY_HASH_A, "C", "D")

    def test_depth_1_returns_direct_successor(
        self, repo: NetworkXGraphRepository
    ) -> None:
        self._build_chain(repo)
        result = repo.neighbors(_DUMMY_HASH_A, "A", max_depth=1)
        assert result == ["B"]

    def test_depth_2_returns_two_hops(self, repo: NetworkXGraphRepository) -> None:
        self._build_chain(repo)
        result = repo.neighbors(_DUMMY_HASH_A, "A", max_depth=2)
        assert set(result) == {"B", "C"}

    def test_depth_0_returns_empty(self, repo: NetworkXGraphRepository) -> None:
        self._build_chain(repo)
        result = repo.neighbors(_DUMMY_HASH_A, "A", max_depth=0)
        assert result == []

    def test_nonexistent_node_returns_empty(
        self, repo: NetworkXGraphRepository
    ) -> None:
        result = repo.neighbors(_DUMMY_HASH_A, "ghost", max_depth=3)
        assert result == []

    def test_no_duplicate_in_diamond_graph(
        self, repo: NetworkXGraphRepository
    ) -> None:
        """A → B, A → C, B → D, C → D 다이아몬드 — D 중복 없음."""
        self._add_abcd_nodes(repo)
        repo.add_edge(_DUMMY_HASH_A, "A", "B")
        repo.add_edge(_DUMMY_HASH_A, "A", "C")
        repo.add_edge(_DUMMY_HASH_A, "B", "D")
        repo.add_edge(_DUMMY_HASH_A, "C", "D")
        result = repo.neighbors(_DUMMY_HASH_A, "A", max_depth=2)
        assert result.count("D") == 1


# ─────────────────────────────────────────────────────────────────────────────
# 통계 (node_count / iter_nodes)
# ─────────────────────────────────────────────────────────────────────────────


class TestStatistics:
    def test_node_count_empty_graph(self, repo: NetworkXGraphRepository) -> None:
        assert repo.node_count(_DUMMY_HASH_A) == 0

    def test_node_count_after_adds(self, repo: NetworkXGraphRepository) -> None:
        repo.add_node(_DUMMY_HASH_A, "n1")
        repo.add_node(_DUMMY_HASH_A, "n2")
        assert repo.node_count(_DUMMY_HASH_A) == 2

    def test_node_count_decreases_after_remove(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "n1")
        repo.add_node(_DUMMY_HASH_A, "n2")
        repo.remove_node(_DUMMY_HASH_A, "n1")
        assert repo.node_count(_DUMMY_HASH_A) == 1

    def test_iter_nodes_yields_all_nodes_with_attrs(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "n1", label="first")
        repo.add_node(_DUMMY_HASH_A, "n2", label="second")
        items = list(repo.iter_nodes(_DUMMY_HASH_A))
        node_ids = set(dict(items).keys())
        assert node_ids == {"n1", "n2"}
        attrs_map = dict(items)
        assert attrs_map["n1"]["label"] == "first"

    def test_iter_nodes_empty_graph_returns_nothing(
        self, repo: NetworkXGraphRepository
    ) -> None:
        assert not list(repo.iter_nodes(_DUMMY_HASH_A))


# ─────────────────────────────────────────────────────────────────────────────
# 영속성 (persist / load)
# ─────────────────────────────────────────────────────────────────────────────


class TestPersistence:
    def test_persist_creates_file(
        self, repo: NetworkXGraphRepository, storage_path: str
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "n1", title="Hello")
        repo.persist(_DUMMY_HASH_A)
        expected = build_graph_path(_DUMMY_HASH_A, storage_path)
        assert expected.exists()

    def test_load_restores_nodes_and_edges(
        self, repo: NetworkXGraphRepository, storage_path: str
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "n1", title="Restored")
        repo.add_node(_DUMMY_HASH_A, "n2")
        repo.add_edge(_DUMMY_HASH_A, "n1", "n2", weight=0.7)
        repo.persist(_DUMMY_HASH_A)

        # 새 인스턴스로 복원
        repo2 = NetworkXGraphRepository(storage_base_path=storage_path)
        repo2.load(_DUMMY_HASH_A)

        # 구조 복원 확인
        assert repo2.has_node(_DUMMY_HASH_A, "n1")
        assert repo2.has_node(_DUMMY_HASH_A, "n2")
        assert repo2.has_edge(_DUMMY_HASH_A, "n1", "n2")

        # 메타데이터(노드/엣지 속성) 복원 확인
        node_attrs = repo2.get_node_attrs(_DUMMY_HASH_A, "n1")
        assert node_attrs is not None
        assert node_attrs["title"] == "Restored"

        edge_attrs = repo2.get_edge_attrs(_DUMMY_HASH_A, "n1", "n2")
        assert edge_attrs is not None
        assert edge_attrs["weight"] == 0.7

    def test_load_absent_file_initializes_empty_graph(
        self, repo: NetworkXGraphRepository
    ) -> None:
        """파일이 없으면 빈 그래프로 조용히 초기화된다."""
        repo.load(_DUMMY_HASH_A)  # Must not raise
        assert repo.node_count(_DUMMY_HASH_A) == 0

    def test_persist_is_atomic_no_partial_write(
        self, repo: NetworkXGraphRepository, storage_path: str
    ) -> None:
        """원자적 쓰기 후 .tmp 파일이 남지 않아야 한다."""
        repo.add_node(_DUMMY_HASH_A, "n1")
        repo.persist(_DUMMY_HASH_A)
        graph_dir = build_graph_path(_DUMMY_HASH_A, storage_path).parent
        tmp_files = list(graph_dir.glob("*.tmp"))
        assert not tmp_files


# ─────────────────────────────────────────────────────────────────────────────
# 테넌트 격리
# ─────────────────────────────────────────────────────────────────────────────


class TestTenantIsolation:
    def test_user_a_nodes_invisible_to_user_b(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "node-a-only")
        assert repo.has_node(_DUMMY_HASH_B, "node-a-only") is False

    def test_user_b_mutation_does_not_affect_user_a(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "shared-name")
        repo.add_node(_DUMMY_HASH_B, "shared-name")
        repo.remove_node(_DUMMY_HASH_B, "shared-name")
        # 사용자 A의 노드는 살아있어야 한다
        assert repo.has_node(_DUMMY_HASH_A, "shared-name") is True

    def test_node_counts_are_independent(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "n1")
        repo.add_node(_DUMMY_HASH_A, "n2")
        repo.add_node(_DUMMY_HASH_B, "n1")
        assert repo.node_count(_DUMMY_HASH_A) == 2
        assert repo.node_count(_DUMMY_HASH_B) == 1

    def test_persist_and_load_tenant_isolation(
        self, repo: NetworkXGraphRepository, storage_path: str
    ) -> None:
        """두 사용자의 파일이 서로 다른 경로에 저장된다."""
        repo.add_node(_DUMMY_HASH_A, "node-a")
        repo.add_node(_DUMMY_HASH_B, "node-b")
        repo.persist(_DUMMY_HASH_A)
        repo.persist(_DUMMY_HASH_B)

        path_a = build_graph_path(_DUMMY_HASH_A, storage_path)
        path_b = build_graph_path(_DUMMY_HASH_B, storage_path)
        assert path_a != path_b
        assert path_a.exists()
        assert path_b.exists()


# ─────────────────────────────────────────────────────────────────────────────
# clear
# ─────────────────────────────────────────────────────────────────────────────


class TestClear:
    def test_clear_removes_all_in_memory_nodes(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "n1")
        repo.add_node(_DUMMY_HASH_A, "n2")
        repo.clear(_DUMMY_HASH_A)
        assert repo.node_count(_DUMMY_HASH_A) == 0

    def test_clear_does_not_delete_persisted_file(
        self, repo: NetworkXGraphRepository, storage_path: str
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "n1")
        repo.persist(_DUMMY_HASH_A)
        repo.clear(_DUMMY_HASH_A)
        assert build_graph_path(_DUMMY_HASH_A, storage_path).exists()

    def test_clear_does_not_affect_other_tenant(
        self, repo: NetworkXGraphRepository
    ) -> None:
        repo.add_node(_DUMMY_HASH_A, "n1")
        repo.add_node(_DUMMY_HASH_B, "n1")
        repo.clear(_DUMMY_HASH_A)
        assert repo.node_count(_DUMMY_HASH_B) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 동시성 (스레드 안전성 스모크 테스트)
# ─────────────────────────────────────────────────────────────────────────────


class TestConcurrency:
    def test_concurrent_add_nodes_no_data_race(
        self, repo: NetworkXGraphRepository
    ) -> None:
        """
        여러 스레드가 동시에 add_node를 호출해도 예외나 데이터 손상이 없음을 확인한다.
        최종 노드 수는 추가된 수와 동일해야 한다.
        """
        n_threads = 10
        n_nodes_per_thread = 20
        errors: list[Exception] = []

        def worker(thread_idx: int) -> None:
            try:
                for i in range(n_nodes_per_thread):
                    repo.add_node(
                        _DUMMY_HASH_A,
                        f"t{thread_idx}-n{i}",
                        thread=thread_idx,
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(idx,)) for idx in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent add_node raised errors: {errors}"
        assert repo.node_count(_DUMMY_HASH_A) == n_threads * n_nodes_per_thread

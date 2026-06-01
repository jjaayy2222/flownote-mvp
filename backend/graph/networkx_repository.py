# backend/graph/networkx_repository.py

"""
NetworkX 기반 인메모리 + 파일시스템 그래프 Repository 구현체 (Phase 4-1).

설계 원칙:
  - hashed_user_id 단위로 독립적인 DiGraph 인스턴스를 관리하여 테넌트 완전 격리.
  - 영속화: GraphML 포맷 + 원자적 쓰기(임시 파일 → rename)로 부분 쓰기 방지.
  - 경로: {STORAGE_BASE_PATH}/graph_data/{hashed_user_id}.graphml
  - 스레드 안전성: 사용자별 Lock으로 동시 쓰기 직렬화 (per-user intra-process lock).
  - PII 보안: user_id 원문은 절대 로그·경로에 기록하지 않는다.
  - neo4j 전환 시: AbstractGraphRepository 인터페이스만 유지하고 이 파일만 교체한다.

GraphML 채택 이유:
  - networkx 표준 직렬화 포맷 (추가 의존성 없음).
  - 노드/엣지 속성을 XML 메타데이터로 손실 없이 보존 (pickle 대비 이식성 우수).
  - neo4j Cypher IMPORT 호환 포맷으로의 변환이 용이.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterator, Generator
from contextlib import contextmanager

import networkx as nx

from backend.graph.base import AbstractGraphRepository, GraphLoadError
from backend.graph.path_utils import build_graph_path

logger = logging.getLogger(__name__)


class NetworkXGraphRepository(AbstractGraphRepository):
    """
    networkx.DiGraph 기반 인메모리 그래프 Repository.

    사용법:
        repo = NetworkXGraphRepository(storage_base_path=cfg.storage_base_path)
        repo.load(hashed_user_id)          # 파일에서 복원 (없으면 빈 그래프)
        repo.add_node(hashed_user_id, "note-uuid", title="My Note", node_type="note")
        repo.add_edge(hashed_user_id, "note-uuid", "tag-python", weight=1.0, edge_type="explicit")
        repo.persist(hashed_user_id)       # 파일시스템 영속화

    스레드 안전성:
        모든 뮤테이션 및 읽기 쿼리는 사용자별 threading.Lock으로 직렬화되어
        동시 변이 중 일관성을 보장한다. (사용자 간에는 완전 병렬 처리 가능)
    """

    def __init__(self, storage_base_path: str) -> None:
        """
        Args:
            storage_base_path: STORAGE_BASE_PATH 환경 변수에서 로드된 루트 경로.
                               PersonalizedRAGConfig.storage_base_path 값을 주입할 것.

        Raises:
            ValueError: storage_base_path가 비어 있는 경우
        """
        if not storage_base_path:
            raise ValueError(
                "NetworkXGraphRepository: 'storage_base_path' must not be empty. "
                "Inject PersonalizedRAGConfig.storage_base_path."
            )
        # 보안: 경로 값 자체는 절대 로그에 기록하지 않는다
        self._storage_base_path: str = storage_base_path

        # 사용자별 DiGraph 인스턴스 맵 — 완전 테넌트 격리
        self._graphs: dict[str, nx.DiGraph] = {}

        # 사용자별 Lock — 동시 뮤테이션 직렬화 (intra-process)
        self._locks: dict[str, threading.Lock] = {}

        # _graphs/_locks 딕셔너리 자체를 보호하는 메타 Lock
        self._meta_lock: threading.Lock = threading.Lock()

    # ─────────────────────────────────────────────────────────────────────
    # 내부 헬퍼
    # ─────────────────────────────────────────────────────────────────────

    def _get_or_create_graph(self, hashed_user_id: str) -> nx.DiGraph:
        """
        사용자 DiGraph를 반환한다. 없으면 빈 DiGraph를 생성하여 등록한다.

        _graphs 딕셔너리 변경은 _meta_lock으로 보호하여 스레드 안전성을 보장한다.
        """
        g = self._graphs.get(hashed_user_id)
        if g is not None:
            return g
        
        with self._meta_lock:
            if hashed_user_id not in self._graphs:
                self._graphs[hashed_user_id] = nx.DiGraph()
            return self._graphs[hashed_user_id]

    def _get_user_lock(self, hashed_user_id: str) -> threading.Lock:
        """사용자별 Lock을 반환하고, 없으면 생성한다 (Double-checked locking)."""
        lock = self._locks.get(hashed_user_id)
        if lock is not None:
            return lock
            
        with self._meta_lock:
            if hashed_user_id not in self._locks:
                self._locks[hashed_user_id] = threading.Lock()
            return self._locks[hashed_user_id]

    def _graph_file_path(self, hashed_user_id: str) -> Path:
        """hashed_user_id에 대한 GraphML 파일 경로를 반환한다."""
        return build_graph_path(hashed_user_id, self._storage_base_path)

    # ─────────────────────────────────────────────────────────────────────
    # 노드 뮤테이션
    # ─────────────────────────────────────────────────────────────────────

    def add_node(
        self,
        hashed_user_id: str,
        node_id: str,
        **attrs: Any,
    ) -> None:
        """
        지정 사용자의 그래프에 노드를 추가(또는 속성 갱신)한다.

        멱등성: 동일 node_id로 재호출 시 속성만 갱신 (networkx add_node 기본 동작).
        """
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._get_or_create_graph(hashed_user_id)
            g.add_node(node_id, **attrs)
            logger.debug(
                "[GRAPH][NX] Node added/updated (node_id_prefix=%s).",
                node_id[:8] if node_id else "<empty>",
            )

    def remove_node(self, hashed_user_id: str, node_id: str) -> None:
        """지정 노드와 연결된 모든 엣지를 제거한다. 없으면 Silent no-op."""
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._get_or_create_graph(hashed_user_id)
            if g.has_node(node_id):
                g.remove_node(node_id)
                logger.debug(
                    "[GRAPH][NX] Node removed (node_id_prefix=%s).",
                    node_id[:8] if node_id else "<empty>",
                )

    def has_node(self, hashed_user_id: str, node_id: str) -> bool:
        """노드 존재 여부를 반환한다."""
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._graphs.get(hashed_user_id)
            return False if g is None else g.has_node(node_id)

    def get_node_attrs(
        self,
        hashed_user_id: str,
        node_id: str,
    ) -> dict[str, Any] | None:
        """노드 속성 딕셔너리를 반환한다. 노드가 없으면 None."""
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._graphs.get(hashed_user_id)
            # 방어적 복사 — 내부 상태 외부 변경 방지
            return None if g is None or not g.has_node(node_id) else dict(g.nodes[node_id])

    # ─────────────────────────────────────────────────────────────────────
    # 엣지 뮤테이션
    # ─────────────────────────────────────────────────────────────────────

    def add_edge(
        self,
        hashed_user_id: str,
        source_id: str,
        target_id: str,
        **attrs: Any,
    ) -> None:
        """
        방향성 엣지를 추가(또는 속성 갱신)한다.

        암묵적 노드 생성:
            source_id/target_id가 없으면 networkx가 자동 노드 생성한다.
            속성이 필요한 경우 add_node()를 명시적으로 먼저 호출할 것.
        """
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._get_or_create_graph(hashed_user_id)
            g.add_edge(source_id, target_id, **attrs)
            logger.debug(
                "[GRAPH][NX] Edge added/updated (src_prefix=%s, tgt_prefix=%s).",
                source_id[:8] if source_id else "<empty>",
                target_id[:8] if target_id else "<empty>",
            )

    def remove_edge(
        self,
        hashed_user_id: str,
        source_id: str,
        target_id: str,
    ) -> None:
        """엣지를 제거한다. 없으면 Silent no-op."""
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._get_or_create_graph(hashed_user_id)
            if g.has_edge(source_id, target_id):
                g.remove_edge(source_id, target_id)
                logger.debug(
                    "[GRAPH][NX] Edge removed (src_prefix=%s, tgt_prefix=%s).",
                    source_id[:8] if source_id else "<empty>",
                    target_id[:8] if target_id else "<empty>",
                )

    def has_edge(
        self,
        hashed_user_id: str,
        source_id: str,
        target_id: str,
    ) -> bool:
        """엣지 존재 여부를 반환한다."""
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._graphs.get(hashed_user_id)
            return False if g is None else g.has_edge(source_id, target_id)

    def get_edge_attrs(
        self,
        hashed_user_id: str,
        source_id: str,
        target_id: str,
    ) -> dict[str, Any] | None:
        """엣지 속성 딕셔너리를 반환한다. 엣지가 없으면 None."""
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._graphs.get(hashed_user_id)
            return None if g is None or not g.has_edge(source_id, target_id) else dict(g.edges[source_id, target_id])

    # ─────────────────────────────────────────────────────────────────────
    # 탐색 (Traversal)
    # ─────────────────────────────────────────────────────────────────────

    def neighbors(
        self,
        hashed_user_id: str,
        node_id: str,
        max_depth: int = 1,
    ) -> list[str]:
        """
        BFS 방식으로 이웃 노드 ID 목록을 반환한다 (시작 노드 미포함).

        Args:
            hashed_user_id: 테넌트 식별자
            node_id       : 탐색 시작 노드
            max_depth     : 최대 탐색 깊이 (GraphConfig.max_traversal_depth 값 주입 권장)

        Returns:
            BFS 탐색 순서의 이웃 노드 ID 목록 (중복 없음)
        """
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._graphs.get(hashed_user_id)

            if g is None or not g.has_node(node_id):
                return []

            visited: set[str] = {node_id}
            result: list[str] = []
            frontier: list[str] = [node_id]

            for _ in range(max_depth):
                next_frontier: list[str] = []
                for current in frontier:
                    for neighbor in g.successors(current):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            result.append(neighbor)
                            next_frontier.append(neighbor)
                if not next_frontier:
                    break
                frontier = next_frontier

            return result

    # ─────────────────────────────────────────────────────────────────────
    # 통계
    # ─────────────────────────────────────────────────────────────────────

    def node_count(self, hashed_user_id: str) -> int:
        """
        현재 노드 수를 반환한다.

        neo4j 마이그레이션 트리거(GRAPH_MIGRATION_NODE_THRESHOLD) 판단 근거로 사용.
        """
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._graphs.get(hashed_user_id)
            return g.number_of_nodes() if g is not None else 0

    def iter_nodes(
        self, hashed_user_id: str
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        """모든 노드를 (node_id, attrs) 튜플로 순회한다."""
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._graphs.get(hashed_user_id)
            if g is None:
                return iter([])
            # 변이 중 순회 오류 방지를 위한 스냅샷 생성
            snapshot = [(node_id, dict(attrs)) for node_id, attrs in g.nodes(data=True)]
        return iter(snapshot)

    # ─────────────────────────────────────────────────────────────────────
    # 영속성 (Persistence)
    # ─────────────────────────────────────────────────────────────────────

    def persist(self, hashed_user_id: str) -> None:
        """
        현재 인메모리 그래프를 GraphML 파일로 원자적 쓰기한다.

        원자적 쓰기 전략:
            1. 임시 파일(.graphml.{uuid}.tmp)에 먼저 기록
            2. os.replace()로 대상 파일에 원자적 교체 (POSIX 보장)
            → 쓰기 도중 크래시 시 기존 파일 손상 방지

        보안:
            - 경로 내 hashed_user_id만 사용 (user_id PII 절대 미포함)
            - 로그에 경로 전체 값 미기록
        """
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            g = self._get_or_create_graph(hashed_user_id)
            target_path = self._graph_file_path(hashed_user_id)

            # 디렉토리 보장 — 부모가 없으면 생성
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 원자적 쓰기: 임시 파일 → rename (확장자 로직과 독립적으로 이름 구성)
            tmp_path = target_path.with_name(
                f"{target_path.name}.{uuid.uuid4().hex}.tmp"
            )

            try:
                nx.write_graphml(g, str(tmp_path))
                os.replace(str(tmp_path), str(target_path))
                logger.info(
                    "[GRAPH][NX] Graph persisted (subdir=%s, nodes=%d, edges=%d).",
                    "graph_data",
                    g.number_of_nodes(),
                    g.number_of_edges(),
                )
            except Exception:
                # 실패 시 임시 파일 정리 시도
                import contextlib
                with contextlib.suppress(OSError):
                    tmp_path.unlink(missing_ok=True)
                logger.exception(
                    "[GRAPH][NX] Failed to persist graph (subdir=%s). "
                    "Temporary file cleaned up.",
                    "graph_data",
                )
                raise

    def load(self, hashed_user_id: str) -> None:
        """
        파일 시스템에서 GraphML을 읽어 인메모리 그래프를 복원한다.

        파일이 없는 경우: 빈 DiGraph 초기화 후 조용히 반환 (예외 없음).
        파일이 손상된 경우: networkx/XML 파싱 예외를 GraphLoadError로 감싸
            호출자가 스토리지 레이어의 구체적 예외에 노출되지 않도록 한다.
            원본 예외는 __cause__ (from exc 체이닝)에 보존되어 디버깅 정보가 유지된다.
            프로그래밍 버그(TypeError 등 파싱 무관 예외)는 의도적으로 통과시켜
            근본 원인 파악을 방해하지 않는다.

        Raises:
            GraphLoadError: GraphML 파싱 실패 시 — 잘못된 XML 구문
                (xml.etree.ElementTree.ParseError) 또는 GraphML 스키마 오류
                (networkx.NetworkXError) 모두 포함.
        """
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            target_path = self._graph_file_path(hashed_user_id)

            if not target_path.exists():
                # 첫 로드 또는 새 사용자 — 빈 그래프 초기화
                self._graphs[hashed_user_id] = nx.DiGraph()
                logger.info(
                    "[GRAPH][NX] No persisted graph found; initialized empty graph "
                    "(subdir=%s).",
                    "graph_data",
                )
                return

            try:
                loaded = nx.read_graphml(str(target_path))
            except (nx.NetworkXError, ET.ParseError) as exc:
                # networkx/XML 파싱 관련 예외만 캡슐화한다.
                # 프로그래밍 버그(TypeError 등)는 의도적으로 통과시켜
                # GraphLoadError로 오해되지 않도록 한다.
                # `from exc` 체이닝으로 원본 예외는 __cause__에 보존된다.
                logger.exception(
                    "[GRAPH][NX] Failed to load graph from file system (file=%s).",
                    target_path.name,  # storage 내부 경로 비노출, 파일명만 기록
                )
                raise GraphLoadError(
                    "Graph file could not be loaded from storage."
                ) from exc

            # read_graphml은 Graph를 반환할 수 있으므로 방향성 보장
            if not isinstance(loaded, nx.DiGraph):
                loaded = nx.DiGraph(loaded)

            self._graphs[hashed_user_id] = loaded
            logger.info(
                "[GRAPH][NX] Graph loaded from file system (subdir=%s, nodes=%d, edges=%d).",
                "graph_data",
                loaded.number_of_nodes(),
                loaded.number_of_edges(),
            )

    def clear(self, hashed_user_id: str) -> None:
        """
        인메모리 그래프를 초기화한다. 파일 시스템의 파일은 삭제하지 않는다.

        사용 사례:
            - 테스트 격리 초기화
            - 메모리 절약을 위한 idle 사용자 그래프 해제
        """
        lock = self._get_user_lock(hashed_user_id)
        with lock:
            self._graphs[hashed_user_id] = nx.DiGraph()
            logger.debug(
                "[GRAPH][NX] In-memory graph cleared (user isolated).",
            )

    @contextmanager
    def stateless_load(self, hashed_user_id: str) -> Generator[None, None, None]:
        """
        일회성 조회를 위해 그래프를 메모리에 로드하고, 블록 종료 시 안전하게 해제하는 컨텍스트 매니저.
        load() 실패 시(예: 파일 손상) 부작용이 발생하지 않도록 is_loaded 상태를 내부에서 관리한다.
        """
        is_loaded = False
        try:
            self.load(hashed_user_id)
            is_loaded = True
            yield
        finally:
            if is_loaded:
                self.clear(hashed_user_id)

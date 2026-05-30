# backend/graph/base.py

"""
지식 그래프 Repository 추상 인터페이스 (Phase 4-1).

설계 원칙:
  - 엔진 불가지론적(Engine-agnostic) ABC — networkx/neo4j 전환 시 이 인터페이스만 유지.
  - 모든 공개 메서드는 hashed_user_id를 받아 테넌트를 식별한다 (user_id(PII) 금지).
  - 노드/엣지 속성은 JSON 직렬화 가능한 타입(str, int, float, bool, None)만 허용한다.
  - 구현체는 이 ABC를 상속하고 모든 추상 메서드를 반드시 구현해야 한다.

사용법:
    class MyGraphRepository(AbstractGraphRepository):
        def add_node(self, hashed_user_id, node_id, **attrs): ...
        ...
"""

from __future__ import annotations

import abc
from typing import Any, Iterator


class GraphError(Exception):
    """그래프 도메인 관련 최상위 예외"""
    pass


class GraphLoadError(GraphError):
    """그래프 데이터를 스토리지에서 불러오는 중 발생하는 예외"""
    pass


class AbstractGraphRepository(abc.ABC):
    """
    엔진 불가지론적 그래프 Repository 추상 기반 클래스.

    테넌트 격리 계약:
        - 모든 뮤테이션/쿼리 메서드는 첫 번째 파라미터로 hashed_user_id를 받는다.
        - hashed_user_id는 compute_hashed_user_id()의 반환값만 허용 (SHA-256 hex 64자).
        - user_id(PII) 원문은 이 클래스의 어떤 메서드에도 전달해선 안 된다.
    """

    # ─────────────────────────────────────────────────────────────────────
    # 노드 뮤테이션
    # ─────────────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def add_node(
        self,
        hashed_user_id: str,
        node_id: str,
        **attrs: Any,
    ) -> None:
        """
        지정 사용자의 그래프에 노드를 추가(또는 속성 갱신)한다.

        멱등성(Idempotent): 동일 node_id로 재호출 시 속성만 갱신한다.

        Args:
            hashed_user_id: 테넌트 식별자 (SHA-256 hex, PII 미포함)
            node_id       : 노드 고유 식별자 (예: 노트 UUID, 태그명)
            **attrs       : 노드 속성 (JSON 직렬화 가능 타입만 허용)
        """

    @abc.abstractmethod
    def remove_node(self, hashed_user_id: str, node_id: str) -> None:
        """
        지정 사용자의 그래프에서 노드 및 연결된 모든 엣지를 제거한다.

        존재하지 않는 node_id에 대해 조용히 무시(Silent no-op)한다.

        Args:
            hashed_user_id: 테넌트 식별자
            node_id       : 제거할 노드 식별자
        """

    @abc.abstractmethod
    def has_node(self, hashed_user_id: str, node_id: str) -> bool:
        """
        지정 사용자의 그래프에 노드가 존재하는지 확인한다.

        Args:
            hashed_user_id: 테넌트 식별자
            node_id       : 확인할 노드 식별자

        Returns:
            노드 존재 여부 (bool)
        """

    @abc.abstractmethod
    def get_node_attrs(
        self,
        hashed_user_id: str,
        node_id: str,
    ) -> dict[str, Any] | None:
        """
        지정 노드의 속성 딕셔너리를 반환한다.

        Args:
            hashed_user_id: 테넌트 식별자
            node_id       : 조회할 노드 식별자

        Returns:
            속성 딕셔너리, 또는 노드가 없으면 None
        """

    # ─────────────────────────────────────────────────────────────────────
    # 엣지 뮤테이션
    # ─────────────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def add_edge(
        self,
        hashed_user_id: str,
        source_id: str,
        target_id: str,
        **attrs: Any,
    ) -> None:
        """
        지정 사용자의 그래프에 방향성 엣지를 추가(또는 속성 갱신)한다.

        멱등성(Idempotent): (source_id, target_id) 쌍이 이미 존재하면 속성만 갱신한다.

        Args:
            hashed_user_id: 테넌트 식별자
            source_id     : 출발 노드 식별자
            target_id     : 도착 노드 식별자
            **attrs       : 엣지 속성 (예: weight=0.8, edge_type="explicit")
        """

    @abc.abstractmethod
    def remove_edge(
        self,
        hashed_user_id: str,
        source_id: str,
        target_id: str,
    ) -> None:
        """
        지정 사용자의 그래프에서 엣지를 제거한다.

        존재하지 않는 엣지에 대해 조용히 무시(Silent no-op)한다.

        Args:
            hashed_user_id: 테넌트 식별자
            source_id     : 출발 노드 식별자
            target_id     : 도착 노드 식별자
        """

    @abc.abstractmethod
    def has_edge(
        self,
        hashed_user_id: str,
        source_id: str,
        target_id: str,
    ) -> bool:
        """
        지정 사용자의 그래프에 엣지가 존재하는지 확인한다.

        Args:
            hashed_user_id: 테넌트 식별자
            source_id     : 출발 노드 식별자
            target_id     : 도착 노드 식별자

        Returns:
            엣지 존재 여부 (bool)
        """

    @abc.abstractmethod
    def get_edge_attrs(
        self,
        hashed_user_id: str,
        source_id: str,
        target_id: str,
    ) -> dict[str, Any] | None:
        """
        지정 엣지의 속성 딕셔너리를 반환한다.

        Args:
            hashed_user_id: 테넌트 식별자
            source_id     : 출발 노드 식별자
            target_id     : 도착 노드 식별자

        Returns:
            속성 딕셔너리, 또는 엣지가 없으면 None
        """

    # ─────────────────────────────────────────────────────────────────────
    # 탐색 (Traversal)
    # ─────────────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def neighbors(
        self,
        hashed_user_id: str,
        node_id: str,
        max_depth: int = 1,
    ) -> list[str]:
        """
        BFS 방식으로 지정 노드의 이웃 노드 ID 목록을 반환한다.

        Args:
            hashed_user_id: 테넌트 식별자
            node_id       : 탐색 시작 노드
            max_depth     : 최대 탐색 깊이 (GraphConfig.max_traversal_depth 기본값 적용 권장)

        Returns:
            발견된 이웃 노드 ID 목록 (시작 노드 미포함, 거리 오름차순)
        """

    # ─────────────────────────────────────────────────────────────────────
    # 통계
    # ─────────────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def node_count(self, hashed_user_id: str) -> int:
        """
        지정 사용자의 그래프 노드 수를 반환한다.

        neo4j 마이그레이션 트리거(GRAPH_MIGRATION_NODE_THRESHOLD) 판단에 사용된다.

        Args:
            hashed_user_id: 테넌트 식별자

        Returns:
            현재 노드 수 (int)
        """

    @abc.abstractmethod
    def iter_nodes(self, hashed_user_id: str) -> Iterator[tuple[str, dict[str, Any]]]:
        """
        지정 사용자 그래프의 모든 노드를 (node_id, attrs) 형태로 순회한다.

        Args:
            hashed_user_id: 테넌트 식별자

        Yields:
            (node_id: str, attrs: dict) 튜플
        """

    # ─────────────────────────────────────────────────────────────────────
    # 영속성 (Persistence)
    # ─────────────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def persist(self, hashed_user_id: str) -> None:
        """
        현재 인메모리 그래프 상태를 파일 시스템에 영속화한다.

        구현 요구사항:
          - 원자적 쓰기 (임시 파일 → rename) 로 부분 쓰기 방지.
          - 디렉토리가 없으면 생성 (parents=True, exist_ok=True).

        Args:
            hashed_user_id: 테넌트 식별자 (파일명 결정에 사용)
        """

    @abc.abstractmethod
    def load(self, hashed_user_id: str) -> None:
        """
        파일 시스템에서 그래프를 인메모리로 복원한다.

        파일이 없는 경우 빈 그래프를 초기화하고 조용히 반환한다 (예외 없음).

        Args:
            hashed_user_id: 테넌트 식별자 (파일명 결정에 사용)
        """

    @abc.abstractmethod
    def clear(self, hashed_user_id: str) -> None:
        """
        지정 사용자의 인메모리 그래프를 초기화한다.
        파일 시스템의 영속화 파일은 삭제하지 않는다.

        Args:
            hashed_user_id: 테넌트 식별자
        """

# backend/graph/analysis.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 4-4: 지식 그래프 연결성 분석 알고리즘 (고립 노트 감지)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 설계 원칙:
#   - 순수 함수(Pure Function) 기반 — 부작용 없음, 단위 테스트 용이.
#   - 엔진 불가지론적 — AbstractGraphRepository 의존 없이 GraphNode/GraphEdge만 사용.
#   - 하드코딩 금지 — 모든 임계값은 환경 변수(ORPHAN_DEGREE_THRESHOLD)에서 로드.
#   - PII 보안 — user_id 원문에 절대 접근하지 않음. GraphNode.user_id_hash만 사용.
#   - 테넌트 격리 — 함수 인자로 이미 격리된 nodes/edges를 받음. 호출 측에서 격리 보장 필요.
#
# [ORPHAN_DEGREE_THRESHOLD 환경 변수 규격]
#   타입  : int
#   기본값: 0   (엣지가 0개인 완전 고립 노드만 감지)
#   범위  : 0 ~ 100
#   파싱 오류 시: 기본값 폴백 + WARNING 로그
#   범위 초과 시: Clamp 처리 + WARNING 로그
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from __future__ import annotations

import logging
import os
from typing import Sequence

from backend.schemas.graph import GraphEdge, GraphNode, NodeType, OrphanNode

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# 환경 변수 상수 (하드코딩 금지)
# ─────────────────────────────────────────

_ENV_ORPHAN_DEGREE_THRESHOLD = "ORPHAN_DEGREE_THRESHOLD"
_DEFAULT_ORPHAN_DEGREE_THRESHOLD: int = 0
_MIN_ORPHAN_DEGREE_THRESHOLD: int = 0
_MAX_ORPHAN_DEGREE_THRESHOLD: int = 100


# ─────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────


def get_orphan_degree_threshold() -> int:
    """
    ORPHAN_DEGREE_THRESHOLD 환경 변수에서 임계값을 로드한다.

    - 환경 변수 미설정 시: 기본값 반환
    - 파싱 실패 시: 기본값 폴백 + WARNING 로그
    - 범위(0~100) 초과 시: Clamp 처리 + WARNING 로그

    이 함수는 매 호출 시 환경 변수를 다시 읽으므로, 런타임 환경 변수 변경도 즉시 반영된다.

    Returns:
        유효한 정수 임계값 (항상 [MIN, MAX] 범위 내 보장)
    """
    raw = os.environ.get(_ENV_ORPHAN_DEGREE_THRESHOLD)
    if raw is None:
        return _DEFAULT_ORPHAN_DEGREE_THRESHOLD

    try:
        value = int(raw.strip())
    except (ValueError, AttributeError):
        logger.warning(
            "[GRAPH][ORPHAN] %s=%r 는 유효하지 않은 정수입니다. 기본값 %d 로 폴백합니다.",
            _ENV_ORPHAN_DEGREE_THRESHOLD,
            raw,
            _DEFAULT_ORPHAN_DEGREE_THRESHOLD,
        )
        return _DEFAULT_ORPHAN_DEGREE_THRESHOLD

    clamped = max(_MIN_ORPHAN_DEGREE_THRESHOLD, min(_MAX_ORPHAN_DEGREE_THRESHOLD, value))
    if clamped != value:
        logger.warning(
            "[GRAPH][ORPHAN] %s=%d 는 허용 범위 [%d, %d] 를 벗어났습니다. %d 로 Clamp 처리합니다.",
            _ENV_ORPHAN_DEGREE_THRESHOLD,
            value,
            _MIN_ORPHAN_DEGREE_THRESHOLD,
            _MAX_ORPHAN_DEGREE_THRESHOLD,
            clamped,
        )
    return clamped


def _build_degree_map(edges: Sequence[GraphEdge]) -> dict[str, int]:
    """
    엣지 목록에서 노드별 전체 차수(in-degree + out-degree) 맵을 계산한다.

    방향 그래프(Directed Graph)에서 고립 여부는 방향에 무관한
    전체 연결 수(in + out)로 판별한다.

    Args:
        edges: 분석 대상 엣지 목록

    Returns:
        {node_id: total_degree} 딕셔너리.
        엣지가 없는 노드는 포함되지 않음 (degree=0으로 간주).
    """
    degree: dict[str, int] = {}
    for edge in edges:
        degree[edge.source] = degree.get(edge.source, 0) + 1
        degree[edge.target] = degree.get(edge.target, 0) + 1
    return degree


# ─────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────


def find_orphan_nodes(
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge],
    degree_threshold: int | None = None,
) -> list[OrphanNode]:
    """
    고립 노트(Orphan Notes)를 필터링하여 반환한다.

    전체 차수(in-degree + out-degree)가 degree_threshold 이하인 노드를
    고립 노드로 분류하고, 차수 오름차순으로 정렬하여 반환한다.

    [감지 제외 대상]
    CATEGORY 노드(Projects/Areas/Resources/Archive)는 구조적 루트 노드이므로
    엣지가 없더라도 고립 감지 대상에서 반드시 제외한다.

    [테넌트 격리 계약]
    이 함수는 이미 테넌트 격리된 nodes/edges를 입력으로 받는다.
    호출 측에서 hashed_user_id 기반으로 필터링된 데이터를 전달해야 한다.
    이 함수 내부에서 추가적인 테넌트 격리를 수행하지 않는다.

    [PII 보안]
    GraphNode.user_id_hash는 mask_pii_id()를 통해 이미 해싱된 값만 허용한다.
    이 함수는 user_id 원문에 접근하지 않는다.

    Args:
        nodes: 분석 대상 그래프 노드 목록 (테넌트 격리 완료)
        edges: 분석 대상 그래프 엣지 목록 (테넌트 격리 완료)
        degree_threshold: 고립 노드 판별 임계값.
                          None이면 ORPHAN_DEGREE_THRESHOLD 환경 변수에서 로드.
                          이 인자를 직접 전달하면 환경 변수보다 우선한다 (테스트 용이성).

    Returns:
        OrphanNode 목록 — 차수 오름차순 정렬.
        빈 그래프이거나 고립 노드가 없으면 빈 리스트를 반환한다.
    """
    if degree_threshold is None:
        degree_threshold = get_orphan_degree_threshold()
    else:
        degree_threshold = max(
            _MIN_ORPHAN_DEGREE_THRESHOLD,
            min(_MAX_ORPHAN_DEGREE_THRESHOLD, degree_threshold),
        )

    degree_map = _build_degree_map(edges)

    orphans: list[OrphanNode] = []
    for node in nodes:
        # CATEGORY 노드는 구조적 루트 노드이므로 고립 감지 제외
        if node.node_type == NodeType.CATEGORY:
            continue

        node_degree = degree_map.get(node.id, 0)
        if node_degree <= degree_threshold:
            orphans.append(
                OrphanNode(
                    id=node.id,
                    label=node.label,
                    node_type=node.node_type,
                    properties=node.properties,
                    degree=node_degree,
                    user_id_hash=node.user_id_hash,
                )
            )
            logger.debug(
                "[GRAPH][ORPHAN] 고립 노드 감지 (id_prefix=%s, degree=%d).",
                node.id[:8] if node.id else "<empty>",
                node_degree,
            )

    # 차수 오름차순 정렬 (degree=0 완전 고립 노드가 최상단)
    orphans.sort(key=lambda n: n.degree)

    logger.info(
        "[GRAPH][ORPHAN] 고립 노드 감지 완료: 전체=%d, 감지=%d, 임계값=%d.",
        len(nodes),
        len(orphans),
        degree_threshold,
    )
    return orphans


__all__ = ["find_orphan_nodes", "get_orphan_degree_threshold"]

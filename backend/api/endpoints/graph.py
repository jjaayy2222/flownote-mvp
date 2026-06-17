# backend/api/endpoints/graph.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 4: 지식 그래프 API 엔드포인트 - v1
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# [SSOT 정책]
# 이 라우터의 모든 응답은 반드시 `backend.schemas.graph`의 모델을 response_model로 선언해야 합니다.
# raw dict 반환은 OpenAPI 스키마 동기화를 깨뜨리므로 절대 허용되지 않습니다.
#
# [버저닝 정책]
# 현재 라우터 prefix: /api/graph (= v1)
# Breaking Change 발생 시 /api/v2/graph 라우터를 신규 생성하고,
# 이 v1 라우터는 Deprecation 헤더를 추가하여 일정 기간 유지합니다.
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.graph.analysis import find_orphan_nodes, get_orphan_degree_threshold
from backend.schemas.graph import (
    GraphDataResponse,
    NodeType,
    OrphanNotesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["Knowledge Graph (v1)"])


from backend.graph.builder import build_graph_data

# ─────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────


@router.get(
    "/data",
    response_model=GraphDataResponse,
    summary="PARA 기반 지식 그래프 데이터 조회",
    description=(
        "PARA 방법론(Projects/Areas/Resources/Archive) 기반으로 구성된 "
        "노트 간의 노드-엣지 데이터를 반환합니다. "
        "프론트엔드 react-force-graph 시각화에 사용됩니다.\n\n"
        "[SSOT] 응답 스키마는 `backend.schemas.graph.GraphDataResponse`를 단일 진실 공급원으로 합니다."
    ),
)
async def get_graph_data() -> GraphDataResponse:
    """
    PARA Graph View를 위한 노드와 엣지 데이터를 SSOT 스키마 형식으로 반환합니다.

    [v1] 현재는 PARA 카테고리 계층 관계(EdgeRelationshipType.PARA_CATEGORY)만 표현합니다.
    Phase 4-1에서 명시적/암묵적 관계 추출 파이프라인이 연동되면 확장됩니다.
    """
    return build_graph_data()


@router.get(
    "/orphans",
    response_model=OrphanNotesResponse,
    summary="고립 노트(Orphan Notes) 감지",
    description=(
        "전체 그래프에서 엣지 차수(Degree)가 0이거나 극도로 낮은 "
        "'고립 노트(Orphan Notes)'를 감지하여 반환합니다.\n\n"
        "임계값은 ORPHAN_DEGREE_THRESHOLD 환경 변수(기본값: 0)로 제어합니다.\n\n"
        "[SSOT] 응답 스키마는 `backend.schemas.graph.OrphanNotesResponse`를 "
        "단일 진실 공급원으로 합니다."
    ),
)
async def get_orphan_notes() -> OrphanNotesResponse:
    """
    고립 노트(Orphan Notes)를 감지하여 OrphanNotesResponse로 반환합니다.

    [알고리즘]
    1. _build_graph_data()로 현재 그래프의 전체 노드/엣지를 로드.
    2. find_orphan_nodes()로 ORPHAN_DEGREE_THRESHOLD 이하 차수의 노드를 필터링.
    3. CATEGORY 노드는 구조적 루트이므로 고립 감지에서 제외.
    4. 차수 오름차순으로 정렬하여 반환.

    [ORPHAN_DEGREE_THRESHOLD]
    - 기본값: 0 (완전 고립 노드만 감지)
    - 범위: 0~100
    - 파싱 실패 시: 기본값 폴백 + WARNING 로그
    """
    graph_data = build_graph_data()

    # CATEGORY 노드를 total_nodes 카운트에서 제외 (분석 대상 노드만 집계)
    analyzable_nodes = [
        node for node in graph_data.nodes if node.node_type != NodeType.CATEGORY
    ]

    threshold = get_orphan_degree_threshold()

    orphans = find_orphan_nodes(
        nodes=analyzable_nodes,
        edges=graph_data.edges,
        degree_threshold=threshold,
    )

    return OrphanNotesResponse(
        orphans=orphans,
        total_nodes=len(analyzable_nodes),
        degree_threshold=threshold,
    )

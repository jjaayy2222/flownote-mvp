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

import random
import logging

from fastapi import APIRouter

from backend.database.connection import DatabaseConnection
from backend.schemas.graph import (
    EdgeRelationshipType,
    GraphDataResponse,
    GraphEdge,
    GraphNode,
    NodeType,
)
from backend.utils.common import mask_pii_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["Knowledge Graph (v1)"])


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
    # ─── PARA 카테고리 노드 (고정 시드 노드) ───────────────────────────────
    # 기존 graph.py의 하드코딩 레이아웃을 기반으로 고정 좌표 부여
    category_positions = {
        "Projects": {"x": 0.0, "y": 0.0},
        "Areas": {"x": 600.0, "y": 0.0},
        "Resources": {"x": 0.0, "y": 600.0},
        "Archive": {"x": 600.0, "y": 600.0},
    }

    nodes: list[GraphNode] = []
    
    for cat in category_positions:
        try:
            pos_x = category_positions[cat]["x"]
            pos_y = category_positions[cat]["y"]
        except KeyError as e:
            # 설정 누락 시 런타임 에러 추적을 용이하게 하기 위한 Descriptive Error
            raise RuntimeError(f"지식 그래프 설정 오류: 카테고리 '{cat}'의 좌표({e})가 누락되었습니다.") from e

        nodes.append(
            GraphNode(
                id=cat,
                label=cat,
                node_type=NodeType.CATEGORY,
                properties={"para_category": cat},
                position_x=pos_x,
                position_y=pos_y,
            )
        )
        
    edges: list[GraphEdge] = []

    # ─── 파일 노드 및 카테고리→파일 엣지 생성 ────────────────────────────────
    try:
        with DatabaseConnection() as db:
            files = db.get_files_with_para()
    except Exception:
        logger.exception("그래프 데이터 조회 중 DB 연결 실패. 빈 그래프를 반환합니다.")
        return GraphDataResponse(nodes=nodes, edges=edges)

    valid_category_ids = set(category_positions)

    file_nodes: list[GraphNode] = []
    file_edges: list[GraphEdge] = []

    for file in files:
        file_id = str(file["id"])
        filename = file.get("filename", "")
        category = file.get("para_category", "")

        if not category or category not in valid_category_ids:
            continue

        # 파일 노드 ID: 'file-{id}' 형식 (GraphEdge.id 규약과 동일)
        file_node_id = f"file-{file_id}"

        # [PII 보안] user_id가 빈 문자열이 아닌 유효한 값인 경우에만 해싱 (Falsy 0 방어 및 "" 결측치 방어)
        raw_user_id = file.get("user_id")
        hashed_uid = mask_pii_id(raw_user_id) if raw_user_id not in (None, "") else None

        # Deterministic position: 파일 ID 시드를 사용하여 리로드 시에도 레이아웃 안정 보장
        rng = random.Random(file_id)
        offset_x = rng.randint(-200, 200)
        offset_y = rng.randint(-200, 200)
        if abs(offset_x) < 80 and abs(offset_y) < 80:
            offset_x += 100 if offset_x >= 0 else -100

        # 중심 카테고리 좌표를 기준으로 난수 오프셋 연산
        base_x = category_positions.get(category, {}).get("x", 0.0)
        base_y = category_positions.get(category, {}).get("y", 0.0)
        
        pos_x = base_x + offset_x
        pos_y = base_y + offset_y

        file_nodes.append(
            GraphNode(
                id=file_node_id,
                label=filename,
                node_type=NodeType.NOTE,
                properties={
                    "para_category": category,
                },
                position_x=pos_x,
                position_y=pos_y,
                user_id_hash=hashed_uid,
            )
        )
        file_edges.append(
            GraphEdge(
                id=f"e-{category}-{file_node_id}",
                source=category,
                target=file_node_id,
                relationship_type=EdgeRelationshipType.PARA_CATEGORY,
                weight=1.0,
            )
        )

    nodes.extend(file_nodes)
    edges.extend(file_edges)

    return GraphDataResponse(nodes=nodes, edges=edges)

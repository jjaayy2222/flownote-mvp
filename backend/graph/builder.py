# backend/graph/builder.py
import logging
import random
from typing import Any

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

def _is_valid_raw_user_id(raw_id: Any) -> bool:
    """
    원본 user_id가 해싱을 수행할 만큼 유효한 값인지 검증하는 헬퍼 함수입니다.
    None, 빈 문자열(""), 공백 문자열("   ") 등은 결측치로 간주하여 False를 반환합니다.
    숫자(예: 0) 등 그 외의 값은 유효한 Falsy/Truthy 값으로 간주하여 True를 반환합니다.
    """
    return raw_id is not None and (not isinstance(raw_id, str) or bool(raw_id.strip()))

# PARA 카테고리 좌표 — 레이아웃 안정성을 위해 모듈 수준 상수로 관리
# 하드코딩으로 보일 수 있으나, 이 값들은 PARA 방법론의 고정 구조를 표현하는
# 디자인 상수(Design Constants)로, 환경 변수화 대상이 아닙니다.
_PARA_CATEGORY_POSITIONS: dict[str, dict[str, float]] = {
    "Projects": {"x": 0.0, "y": 0.0},
    "Areas": {"x": 600.0, "y": 0.0},
    "Resources": {"x": 0.0, "y": 600.0},
    "Archive": {"x": 600.0, "y": 600.0},
}

def build_graph_data() -> GraphDataResponse:
    """
    PARA 기반 지식 그래프 데이터를 DB에서 조회하여 GraphDataResponse를 빌드한다.

    [책임 분리]
    - API 엔드포인트(get_graph_data, get_orphan_notes) 및 백그라운드 태스크에서 재사용합니다.
    - DB 연결 실패 시 CATEGORY 노드만 포함한 빈 응답을 반환합니다 (조용한 폴백).

    Returns:
        GraphDataResponse (nodes + edges)
    """
    # ─── PARA 카테고리 노드 (고정 시드 노드) ───────────────────────────────
    nodes: list[GraphNode] = []
    for cat, pos in _PARA_CATEGORY_POSITIONS.items():
        try:
            pos_x = pos["x"]
            pos_y = pos["y"]
        except KeyError as e:
            raise RuntimeError(
                f"지식 그래프 설정 오류: 카테고리 '{cat}'의 좌표({e})가 누락되었습니다."
            ) from e

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

    valid_category_ids = set(_PARA_CATEGORY_POSITIONS)

    file_nodes: list[GraphNode] = []
    file_edges: list[GraphEdge] = []

    for file in files:
        file_id = str(file.get("id"))
        filename = file.get("filename", "")
        category = file.get("para_category", "")

        if not category or category not in valid_category_ids:
            continue

        # 파일 노드 ID: 'file-{id}' 형식 (GraphEdge.id 규약과 동일)
        file_node_id = f"file-{file_id}"

        # [PII 보안] user_id가 유효한 값(공백 제외)인 경우에만 해싱
        raw_user_id = file.get("user_id")
        hashed_uid = mask_pii_id(raw_user_id) if _is_valid_raw_user_id(raw_user_id) else None

        # Deterministic position: 파일 ID 시드를 사용하여 리로드 시에도 레이아웃 안정 보장
        rng = random.Random(file_id)
        offset_x = rng.randint(-200, 200)
        offset_y = rng.randint(-200, 200)
        if abs(offset_x) < 80 and abs(offset_y) < 80:
            offset_x += 100 if offset_x >= 0 else -100

        base_x = _PARA_CATEGORY_POSITIONS.get(category, {}).get("x", 0.0)
        base_y = _PARA_CATEGORY_POSITIONS.get(category, {}).get("y", 0.0)

        file_nodes.append(
            GraphNode(
                id=file_node_id,
                label=filename,
                node_type=NodeType.NOTE,
                properties={
                    "para_category": category,
                },
                position_x=base_x + offset_x,
                position_y=base_y + offset_y,
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

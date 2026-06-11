# backend/celery_app/tasks/graph.py

import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from backend.celery_app.celery import app
from backend.graph.builder import build_graph_data
from backend.graph.analysis import find_orphan_nodes, get_orphan_degree_threshold
from backend.graph.similarity import (
    find_link_recommendations,
    get_link_similarity_threshold,
    get_max_recommendations_per_orphan,
)
from backend.graph.notifications import send_link_recommendations
from backend.schemas.graph import (
    GraphDataResponse,
    GraphEdge,
    GraphNode,
    LinkRecommendationResult,
    NodeType,
    OrphanNode,
)

logger = logging.getLogger(__name__)

# 임베딩 파이프라인 기능 플래그 (현재 DB 임베딩 부재로 False)
_EMBEDDINGS_ENABLED = os.environ.get("FEATURE_ENABLE_LINK_RECOMMENDATIONS", "false").lower() == "true"

# ─────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────

_MAX_MISSING_UID_SAMPLES = 5


def _collect_category_ids(graph_data: GraphDataResponse) -> set[str]:
    """PARA 카테고리 노드 ID를 수집한다 (테넌트 간 공용 엔드포인트)."""
    return {n.id for n in graph_data.nodes if n.node_type == NodeType.CATEGORY}


@dataclass
class UserGroupingResult:
    nodes_by_user: Dict[str, List[GraphNode]]
    missing_count: int
    missing_samples: List[str]


def _group_nodes_by_user(graph_data: GraphDataResponse) -> UserGroupingResult:
    """비CATEGORY 노드를 user_id_hash 기준으로 그룹화한다."""
    nodes_by_user: Dict[str, List[GraphNode]] = defaultdict(list)
    missing_count = 0
    missing_samples: List[str] = []

    for node in graph_data.nodes:
        if node.node_type == NodeType.CATEGORY:
            continue
        if not node.user_id_hash:
            missing_count += 1
            if len(missing_samples) < _MAX_MISSING_UID_SAMPLES:
                missing_samples.append(node.id)
            continue
        nodes_by_user[node.user_id_hash].append(node)

    return UserGroupingResult(nodes_by_user, missing_count, missing_samples)


def _filter_user_edges(
    graph_data: GraphDataResponse,
    user_node_ids: set[str],
    category_ids: set[str],
) -> List[GraphEdge]:
    """
    해당 사용자 노드 또는 글로벌 CATEGORY 노드를 양 끝점으로 갖는 엣지만 반환한다.
    타 사용자 노드 식별자가 끝점에 포함된 엣지는 교차 접근 차단을 위해 제외한다.
    """
    valid_ids = user_node_ids | category_ids
    return [e for e in graph_data.edges if e.source in valid_ids and e.target in valid_ids]


def _load_embeddings_for_nodes(node_ids: list[str]) -> dict[str, list[float]]:
    """Return {node_id: embedding_vector} for given IDs.

    현재는 임베딩 컬럼/테이블이 없어 빈 딕셔너리를 반환합니다.
    추후 DB/캐시에서 임베딩을 조회하도록 교체합니다.
    """
    # TODO: DB/캐시에서 임베딩 로드 로직으로 교체
    return {}


def _run_recommendation_pipeline(
    uid: str,
    orphans: List[OrphanNode],
    user_nodes: List[GraphNode],
    similarity_threshold: float,
    max_per_orphan: int,
    task_name: str,
) -> Optional[LinkRecommendationResult]:
    """
    단일 사용자 컨텍스트에서 연결 추천 파이프라인을 실행한다.

    고립 노드와 비고립 노드 간 임베딩 벡터 유사도를 측정하고,
    임계값 이상인 쌍에 대해 알림을 전송한다.

    Returns:
        LinkRecommendationResult — 임베딩이 없어 건너뛴 경우 None 반환.
    """
    orphan_ids = {o.id for o in orphans}
    candidate_nodes = [n for n in user_nodes if n.id not in orphan_ids]

    orphan_embeddings = _load_embeddings_for_nodes([o.id for o in orphans])
    candidate_embeddings = _load_embeddings_for_nodes([n.id for n in candidate_nodes])

    if not orphan_embeddings or not candidate_embeddings:
        logger.debug(
            "[%s] user_id_hash=%s 컨텍스트: 임베딩 데이터 없음 — 연결 추천 건너뜀.",
            task_name, uid,
        )
        return None

    recommendations = find_link_recommendations(
        orphan_nodes=orphans,
        candidate_nodes=candidate_nodes,
        orphan_embeddings=orphan_embeddings,
        candidate_embeddings=candidate_embeddings,
        similarity_threshold=similarity_threshold,
        max_per_orphan=max_per_orphan,
    )
    notifications = send_link_recommendations(recommendations)

    return LinkRecommendationResult(
        total_orphans_analyzed=len(orphan_embeddings),
        total_candidates_analyzed=len(candidate_embeddings),
        total_recommendations=len(recommendations),
        total_notifications_sent=len(notifications),
        similarity_threshold=similarity_threshold,
    )


# ─────────────────────────────────────────
# Celery 태스크
# ─────────────────────────────────────────


@app.task(bind=True)
def detect_orphan_notes_for_all_users(self):
    """
    [고립 노트 감지 + 연결 추천 워커]
    전체 그래프 데이터에서 사용자별로 컨텍스트를 완벽히 격리한 후 고립 노트를 스캔하고,
    벡터 유사도가 높은 노드 쌍을 발굴하여 연결(Link) 추천 알림을 전송합니다.

    [처리 단계]
    1. 전체 그래프 데이터 로드
    2. hashed_user_id 기반 테넌트 격리 컨텍스트 구성
    3. 격리된 컨텍스트 내에서 고립 노드 감지
    4. 고립 노드 ↔ 비고립 노드 간 벡터 유사도 측정 및 추천 쌍 발굴
    5. 임계값 이상 추천 쌍에 대한 앱 내 알림 전송

    (Data Leakage 방지: 타 사용자의 노트 내용 섞임 원천 차단)
    """
    task_name = "detect-orphan-notes"
    logger.info("[%s] 전역 고립 노트 스캔 + 연결 추천 스케줄러가 시작되었습니다.", task_name)

    graph_data = build_graph_data()
    orphan_threshold = get_orphan_degree_threshold()

    if not _EMBEDDINGS_ENABLED:
        logger.info(
            "[%s] 임베딩 파이프라인이 비활성화되어 있습니다. "
            "고립 노드 감지만 수행하며, 연결 추천은 건너뜁니다.",
            task_name
        )
        similarity_threshold = 0.0
        max_per_orphan = 0
    else:
        similarity_threshold = get_link_similarity_threshold()
        max_per_orphan = get_max_recommendations_per_orphan()

    category_ids = _collect_category_ids(graph_data)
    grouping = _group_nodes_by_user(graph_data)
    nodes_by_user = grouping.nodes_by_user

    if grouping.missing_count > 0:
        logger.warning(
            "[%s] user_id_hash가 없는 노드가 총 %d개 발견되었습니다. "
            "보안 격리를 위해 스캔에서 제외합니다. (샘플 node_id: %s%s)",
            task_name,
            grouping.missing_count,
            grouping.missing_samples,
            " ..." if grouping.missing_count > _MAX_MISSING_UID_SAMPLES else "",
        )

    users_scanned = len(nodes_by_user)
    total_orphans_found = 0
    agg_recommendations = 0
    agg_notifications_sent = 0

    logger.info("[%s] 총 %d명의 사용자 격리 컨텍스트가 준비되었습니다.", task_name, users_scanned)

    for uid, user_nodes in nodes_by_user.items():
        user_node_ids = {n.id for n in user_nodes}
        user_edges = _filter_user_edges(graph_data, user_node_ids, category_ids)

        orphans = find_orphan_nodes(
            nodes=user_nodes,
            edges=user_edges,
            degree_threshold=orphan_threshold,
        )
        if not orphans:
            continue

        logger.info(
            "[%s] user_id_hash=%s 컨텍스트에서 %d개의 고립 노트를 발견했습니다.",
            task_name, uid, len(orphans),
        )
        total_orphans_found += len(orphans)

        if not _EMBEDDINGS_ENABLED:
            # 추천이 비활성화된 경우, 고립 노트 감지만 수행
            continue

        if pipeline_result := _run_recommendation_pipeline(
            uid=uid,
            orphans=orphans,
            user_nodes=user_nodes,
            similarity_threshold=similarity_threshold,
            max_per_orphan=max_per_orphan,
            task_name=task_name,
        ):
            agg_recommendations += pipeline_result.total_recommendations
            agg_notifications_sent += pipeline_result.total_notifications_sent

    if _EMBEDDINGS_ENABLED:
        logger.info(
            "[%s] 전역 스캔 완료: users=%d, orphans=%d, recommendations=%d, notifications=%d",
            task_name, users_scanned, total_orphans_found, agg_recommendations, agg_notifications_sent,
        )
        return (
            f"Success: {users_scanned} users scanned, "
            f"{total_orphans_found} orphans found, "
            f"{agg_recommendations} link recommendations generated, "
            f"{agg_notifications_sent} notifications sent."
        )
    else:
        logger.info(
            "[%s] 전역 스캔 완료: users=%d, orphans=%d (연결 추천 비활성화)",
            task_name, users_scanned, total_orphans_found,
        )
        return (
            f"Success: {users_scanned} users scanned, "
            f"{total_orphans_found} orphans found (link recommendations disabled)."
        )

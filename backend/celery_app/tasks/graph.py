# backend/celery_app/tasks/graph.py

import logging
from collections import defaultdict
from typing import Dict, List

from backend.celery_app.celery import app
from backend.api.endpoints.graph import _build_graph_data
from backend.graph.analysis import find_orphan_nodes, get_orphan_degree_threshold
from backend.schemas.graph import NodeType, GraphNode

logger = logging.getLogger(__name__)

@app.task(bind=True)
def detect_orphan_notes_for_all_users(self):
    """
    [고립 노트 감지 워커]
    전체 그래프 데이터에서 사용자별로 컨텍스트를 완벽히 격리한 후 고립 노트를 스캔합니다.
    (Data Leakage 방지: 타 사용자의 노트 내용 섞임 원천 차단)
    """
    task_name = "detect-orphan-notes"
    logger.info("[%s] 전역 고립 노트 스캔 스케줄러가 시작되었습니다.", task_name)
    
    # 1. 전체 데이터베이스에서 노드와 엣지 빌드 (내부적으로 PARA CATEGORY 등 포함)
    graph_data = _build_graph_data()
    threshold = get_orphan_degree_threshold()
    
    # 2. 사용자별 노드 그룹화 (보안 필수 요건: hashed_user_id 기반 컨텍스트 주입 및 격리)
    nodes_by_user: Dict[str, List[GraphNode]] = defaultdict(list)
    
    for node in graph_data.nodes:
        if node.node_type == NodeType.CATEGORY:
            continue
        
        # 보안 장치: PII 마스킹된 hashed_user_id를 기준 키로 사용
        # 식별되지 않은 파일의 경우 "unassigned" 풀로 격리
        uid = node.user_id_hash or "unassigned"
        nodes_by_user[uid].append(node)
        
    total_orphans_found = 0
    users_scanned = len(nodes_by_user)
    
    logger.info("[%s] 총 %d명의 사용자 격리 컨텍스트가 준비되었습니다.", task_name, users_scanned)
    
    # 3. 각 격리된 테넌트 컨텍스트 내에서 스캔 수행
    for uid, user_nodes in nodes_by_user.items():
        logger.debug("[%s] 사용자 컨텍스트 스캔 시작 (user_id_hash=%s, 노드 수=%d)", task_name, uid, len(user_nodes))
        
        # 엣지 필터링: 해당 사용자의 노드 간 연결만 추출 (교차 접근 차단)
        user_node_ids = {n.id for n in user_nodes}
        user_edges = [
            e for e in graph_data.edges 
            if e.source in user_node_ids or e.target in user_node_ids
        ]
        
        # 해당 사용자 컨텍스트 안에서만 orphan 판별
        if orphans := find_orphan_nodes(
            nodes=user_nodes,
            edges=user_edges,
            degree_threshold=threshold,
        ):
            logger.info(
                "[%s] user_id_hash=%s 컨텍스트에서 %d개의 고립 노트를 발견했습니다.", 
                task_name, uid, len(orphans)
            )
            total_orphans_found += len(orphans)
            
            # TODO: 향후 이 시점에서 사용자에게 '연결 추천' Notification/Email 트리거 로직 추가 가능
            
    logger.info("[%s] 전역 스캔 완료. 총 %d명의 사용자에 대해 %d개의 고립 노트를 감지했습니다.", task_name, users_scanned, total_orphans_found)
    
    return f"Success: {users_scanned} users scanned, {total_orphans_found} orphans found."

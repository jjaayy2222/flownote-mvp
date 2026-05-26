# backend/core/config/graph.py

"""
지식 그래프 설정 SSOT (Phase 4-0).

환경 변수 키, 기본값, 유효 범위만 정의합니다.
로딩·Clamping·Subsystem 등록은 GraphEngineConfig(config_validator.py) 책임입니다.
"""

from dataclasses import dataclass

from backend.config import ConfigRange

# 환경 변수 키 (문자열 하드코딩 금지 — 모듈 SSOT)
ENV_MAX_TRAVERSAL_DEPTH = "GRAPH_MAX_TRAVERSAL_DEPTH"
ENV_MAX_GRAPH_NODES = "NEXT_PUBLIC_MAX_GRAPH_NODES"
ENV_DB_URL = "GRAPH_DB_URL"
ENV_MIGRATION_NODE_THRESHOLD = "GRAPH_MIGRATION_NODE_THRESHOLD"
ENV_MIGRATION_CONCURRENCY_THRESHOLD = "GRAPH_MIGRATION_CONCURRENCY_THRESHOLD"

# 기본값 (v9.4_knowledge_graph_tasks.md)
DEFAULT_MAX_TRAVERSAL_DEPTH = 3
DEFAULT_MAX_GRAPH_NODES = 500
DEFAULT_DB_URL = ""
DEFAULT_MIGRATION_NODE_THRESHOLD = 10000
DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD = 10

# Clamping 범위
MAX_TRAVERSAL_DEPTH_RANGE = ConfigRange(min=1, max=5)
MAX_GRAPH_NODES_RANGE = ConfigRange(min=50, max=2000)
MIGRATION_NODE_THRESHOLD_RANGE = ConfigRange(min=5000, max=50000)
MIGRATION_CONCURRENCY_THRESHOLD_RANGE = ConfigRange(min=5, max=100)


@dataclass
class GraphConfig:
    """
    지식 그래프 런타임 설정 스키마 (인스턴스 필드만).

    상수(키·기본값·범위)는 이 모듈의 모듈 레벨 이름을 import하여 사용합니다.
    OS 환경 변수 읽기는 GraphEngineConfig에서만 수행합니다.
    """

    max_traversal_depth: int = DEFAULT_MAX_TRAVERSAL_DEPTH
    max_graph_nodes: int = DEFAULT_MAX_GRAPH_NODES
    db_url: str = DEFAULT_DB_URL
    migration_node_threshold: int = DEFAULT_MIGRATION_NODE_THRESHOLD
    migration_concurrency_threshold: int = DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD


def _ensure_default_in_range(name: str, val: int, r: ConfigRange) -> None:
    if not (r.min <= val <= r.max):
        raise RuntimeError(
            f"[GRAPH][CONFIG][INVARIANT ERROR] Default {name}={val} is outside "
            f"allowed range [{r.min}, {r.max}]. Check graph.py constants."
        )


_DEFAULT_INVARIANTS: tuple[tuple[str, int, ConfigRange], ...] = (
    ("MAX_TRAVERSAL_DEPTH", DEFAULT_MAX_TRAVERSAL_DEPTH, MAX_TRAVERSAL_DEPTH_RANGE),
    ("MAX_GRAPH_NODES", DEFAULT_MAX_GRAPH_NODES, MAX_GRAPH_NODES_RANGE),
    (
        "MIGRATION_NODE_THRESHOLD",
        DEFAULT_MIGRATION_NODE_THRESHOLD,
        MIGRATION_NODE_THRESHOLD_RANGE,
    ),
    (
        "MIGRATION_CONCURRENCY_THRESHOLD",
        DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD,
        MIGRATION_CONCURRENCY_THRESHOLD_RANGE,
    ),
)

for _name, _val, _range in _DEFAULT_INVARIANTS:
    _ensure_default_in_range(_name, _val, _range)

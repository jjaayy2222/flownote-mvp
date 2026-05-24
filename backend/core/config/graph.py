# backend/core/config/graph.py

"""
GraphConfig — Phase 4 (Knowledge Graph) 설정 스키마 및 기본값 정의
==================================================================

역할 (4-0 SSOT 정책에 따른 책임 분리):
  이 모듈은 지식 그래프 관련 환경 변수의 '스키마, 환경 변수 키, 기본값, 유효 범위'만 정의합니다.
  실제 OS 환경 변수 로딩, Clamping, Subsystem(DEGRADED) 등록은
  4-5 정책에 따라 `backend/core/config_validator.py`의 GraphValidator에 위임됩니다.

하드코딩 금지:
  모든 수치 상수·환경 변수 키 문자열은 이 모듈에만 중앙 정의합니다.
  개별 모듈에서 값을 복사하거나 재정의하는 것을 금지합니다.

민감 정보 보호:
  `GRAPH_DB_URL` 등 연결 문자열은 로그에 원문을 남기지 않으며,
  사용자 식별은 hashed_user_id 기반 테넌트 격리 정책을 따릅니다.
"""

from dataclasses import dataclass, field
from typing import ClassVar

from backend.config import ConfigRange

# ─────────────────────────────────────────────────────────────────────────────
# 환경 변수 키 상수 (문자열 하드코딩 방지)
# ─────────────────────────────────────────────────────────────────────────────

_ENV_MAX_TRAVERSAL_DEPTH: str = "GRAPH_MAX_TRAVERSAL_DEPTH"
_ENV_MAX_GRAPH_NODES: str = "NEXT_PUBLIC_MAX_GRAPH_NODES"
_ENV_DB_URL: str = "GRAPH_DB_URL"
_ENV_MIGRATION_NODE_THRESHOLD: str = "GRAPH_MIGRATION_NODE_THRESHOLD"
_ENV_MIGRATION_CONCURRENCY_THRESHOLD: str = "GRAPH_MIGRATION_CONCURRENCY_THRESHOLD"

# ─────────────────────────────────────────────────────────────────────────────
# 유효 범위 상수 (Clamping 규칙 중앙 정의 — v9.4_knowledge_graph_tasks.md SSOT)
# ─────────────────────────────────────────────────────────────────────────────

_MAX_TRAVERSAL_DEPTH_RANGE: ConfigRange = ConfigRange(min=1, max=5)
_MAX_GRAPH_NODES_RANGE: ConfigRange = ConfigRange(min=50, max=2000)
_MIGRATION_NODE_THRESHOLD_RANGE: ConfigRange = ConfigRange(min=5000, max=50000)
_MIGRATION_CONCURRENCY_THRESHOLD_RANGE: ConfigRange = ConfigRange(min=5, max=100)

# ─────────────────────────────────────────────────────────────────────────────
# 기본값 상수 (Magic Numbers 제거)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_MAX_TRAVERSAL_DEPTH: int = 3
_DEFAULT_MAX_GRAPH_NODES: int = 500
_DEFAULT_DB_URL: str = ""
_DEFAULT_MIGRATION_NODE_THRESHOLD: int = 10000
_DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD: int = 10

# ─────────────────────────────────────────────────────────────────────────────
# 공개 상수 별칭 (외부·Validator 참조용)
# ─────────────────────────────────────────────────────────────────────────────

GRAPH_ENV_MAX_TRAVERSAL_DEPTH: str = _ENV_MAX_TRAVERSAL_DEPTH
GRAPH_ENV_MAX_GRAPH_NODES: str = _ENV_MAX_GRAPH_NODES
GRAPH_ENV_DB_URL: str = _ENV_DB_URL
GRAPH_ENV_MIGRATION_NODE_THRESHOLD: str = _ENV_MIGRATION_NODE_THRESHOLD
GRAPH_ENV_MIGRATION_CONCURRENCY_THRESHOLD: str = _ENV_MIGRATION_CONCURRENCY_THRESHOLD

GRAPH_DEFAULT_MAX_TRAVERSAL_DEPTH: int = _DEFAULT_MAX_TRAVERSAL_DEPTH
GRAPH_DEFAULT_MAX_GRAPH_NODES: int = _DEFAULT_MAX_GRAPH_NODES
GRAPH_DEFAULT_DB_URL: str = _DEFAULT_DB_URL
GRAPH_DEFAULT_MIGRATION_NODE_THRESHOLD: int = _DEFAULT_MIGRATION_NODE_THRESHOLD
GRAPH_DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD: int = (
    _DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD
)

GRAPH_MAX_TRAVERSAL_DEPTH_RANGE: ConfigRange = _MAX_TRAVERSAL_DEPTH_RANGE
GRAPH_MAX_GRAPH_NODES_RANGE: ConfigRange = _MAX_GRAPH_NODES_RANGE
GRAPH_MIGRATION_NODE_THRESHOLD_RANGE: ConfigRange = _MIGRATION_NODE_THRESHOLD_RANGE
GRAPH_MIGRATION_CONCURRENCY_THRESHOLD_RANGE: ConfigRange = (
    _MIGRATION_CONCURRENCY_THRESHOLD_RANGE
)


# ─────────────────────────────────────────────────────────────────────────────
# GraphConfig 데이터 클래스 (명시적 타입 스키마 — 로딩 로직 없음)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class GraphConfig:
    """
    지식 그래프 파이프라인 런타임 설정 스키마.

    이 클래스는 필드·기본값·환경 변수 키·유효 범위의 SSOT입니다.
    `load()` 등 OS 환경 변수 읽기는 GraphValidator(config_validator.py)에서만 수행합니다.

    사용 예시 (Validator 구현 후):
        config: GraphConfig = graph_validator.load_graph_config()
        depth = config.max_traversal_depth
    """

    max_traversal_depth: int = field(
        default_factory=lambda: _DEFAULT_MAX_TRAVERSAL_DEPTH
    )
    max_graph_nodes: int = field(default_factory=lambda: _DEFAULT_MAX_GRAPH_NODES)
    db_url: str = field(default_factory=lambda: _DEFAULT_DB_URL)
    migration_node_threshold: int = field(
        default_factory=lambda: _DEFAULT_MIGRATION_NODE_THRESHOLD
    )
    migration_concurrency_threshold: int = field(
        default_factory=lambda: _DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD
    )

    ENV_MAX_TRAVERSAL_DEPTH: ClassVar[str] = _ENV_MAX_TRAVERSAL_DEPTH
    ENV_MAX_GRAPH_NODES: ClassVar[str] = _ENV_MAX_GRAPH_NODES
    ENV_DB_URL: ClassVar[str] = _ENV_DB_URL
    ENV_MIGRATION_NODE_THRESHOLD: ClassVar[str] = _ENV_MIGRATION_NODE_THRESHOLD
    ENV_MIGRATION_CONCURRENCY_THRESHOLD: ClassVar[str] = (
        _ENV_MIGRATION_CONCURRENCY_THRESHOLD
    )

    DEFAULT_MAX_TRAVERSAL_DEPTH: ClassVar[int] = _DEFAULT_MAX_TRAVERSAL_DEPTH
    DEFAULT_MAX_GRAPH_NODES: ClassVar[int] = _DEFAULT_MAX_GRAPH_NODES
    DEFAULT_DB_URL: ClassVar[str] = _DEFAULT_DB_URL
    DEFAULT_MIGRATION_NODE_THRESHOLD: ClassVar[int] = _DEFAULT_MIGRATION_NODE_THRESHOLD
    DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD: ClassVar[int] = (
        _DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD
    )

    MAX_TRAVERSAL_DEPTH_RANGE: ClassVar[ConfigRange] = _MAX_TRAVERSAL_DEPTH_RANGE
    MAX_GRAPH_NODES_RANGE: ClassVar[ConfigRange] = _MAX_GRAPH_NODES_RANGE
    MIGRATION_NODE_THRESHOLD_RANGE: ClassVar[ConfigRange] = (
        _MIGRATION_NODE_THRESHOLD_RANGE
    )
    MIGRATION_CONCURRENCY_THRESHOLD_RANGE: ClassVar[ConfigRange] = (
        _MIGRATION_CONCURRENCY_THRESHOLD_RANGE
    )


# ─────────────────────────────────────────────────────────────────────────────
# 모듈 로드 시점 기본값 정합성 검사 (Fail-fast — Python -O에서도 보장)
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_default_in_range(name: str, val: int, r: ConfigRange) -> None:
    if not (r.min <= val <= r.max):
        raise RuntimeError(
            f"[GRAPH][CONFIG][INVARIANT ERROR] Default {name}={val} is outside "
            f"allowed range [{r.min}, {r.max}]. Check graph.py constants."
        )


_ensure_default_in_range(
    "MAX_TRAVERSAL_DEPTH",
    _DEFAULT_MAX_TRAVERSAL_DEPTH,
    _MAX_TRAVERSAL_DEPTH_RANGE,
)
_ensure_default_in_range(
    "MAX_GRAPH_NODES", _DEFAULT_MAX_GRAPH_NODES, _MAX_GRAPH_NODES_RANGE
)
_ensure_default_in_range(
    "MIGRATION_NODE_THRESHOLD",
    _DEFAULT_MIGRATION_NODE_THRESHOLD,
    _MIGRATION_NODE_THRESHOLD_RANGE,
)
_ensure_default_in_range(
    "MIGRATION_CONCURRENCY_THRESHOLD",
    _DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD,
    _MIGRATION_CONCURRENCY_THRESHOLD_RANGE,
)

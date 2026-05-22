# backend/schemas/graph.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 4: 지식 그래프 스키마 - 단일 진실 공급원 (SSOT)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# [SSOT 정책] 이 파일은 지식 그래프의 모든 데이터 타입에 대한 단일 진실 공급원입니다.
# - 백엔드: 이 모델만을 응답 타입으로 사용해야 합니다 (raw dict 반환 금지).
# - 프론트엔드: OpenAPI 스키마를 통해 자동 생성된 타입만 사용해야 합니다.
#   (frontend 내 Node, Link 타입 수동 하드코딩 절대 금지)
#
# [버저닝 정책]
# Breaking Change 발생 시 API v2 네임스페이스를 새로 생성하고,
# 이 v1 모델은 하위 호환성 유지를 위해 Deprecation 기간 동안 보존합니다.
# 직접 삭제하지 마세요.
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
import re

from backend.utils.common import INVALID_PII_SENTINEL

# ─────────────────────────────────────────
# Regex Patterns (Performance Optimization)
# ─────────────────────────────────────────
USER_ID_HASH_PATTERN: re.Pattern[str] = re.compile(r"^(?:[a-f0-9]{12}|[a-f0-9]{64})$")


# ─────────────────────────────────────────
# Enums (확장 가능한 관계 유형)
# ─────────────────────────────────────────


class EdgeRelationshipType(str, Enum):
    """
    노트 간 관계의 유형.

    - EXPLICIT_LINK: 사용자가 위키링크([[노트명]]) 또는 태그로 직접 명시한 관계.
    - IMPLICIT_SEMANTIC: LLM/NLP 분석을 통해 자동으로 발견된 의미론적 관계.
    - PARA_CATEGORY: PARA 방법론(Projects/Areas/Resources/Archive)에 따른 계층 관계.
    """

    EXPLICIT_LINK = "explicit_link"
    IMPLICIT_SEMANTIC = "implicit_semantic"
    PARA_CATEGORY = "para_category"


class NodeType(str, Enum):
    """
    그래프 노드의 종류.

    - NOTE: 실제 마크다운 노트 문서.
    - KEYWORD: LLM/NLP 분석으로 추출된 핵심 키워드.
    - TAG: 사용자가 직접 부여한 태그.
    - CATEGORY: PARA 카테고리 (Projects, Areas, Resources, Archive).
    """

    NOTE = "note"
    KEYWORD = "keyword"
    TAG = "tag"
    CATEGORY = "category"


# ─────────────────────────────────────────
# Core Graph Models (v1)
# ─────────────────────────────────────────


class GraphNode(BaseModel):
    """
    지식 그래프의 노드(정점) 모델. [SSOT - v1]

    각 노드는 노트, 키워드, 태그, 또는 PARA 카테고리 중 하나를 나타냅니다.

    [PII 보안 정책]
    user_id는 원본 값을 절대 직렬화하지 않습니다.
    user_id_hash 필드만 외부에 노출되며, mask_pii_id()를 통해 자동 마스킹됩니다.
    """

    id: str = Field(
        ...,
        description="노드의 고유 식별자. 노트의 경우 파일 경로 기반 해시값을 권장.",
    )
    label: str = Field(
        ...,
        description="시각화 UI에 표시될 노드의 이름. (예: 노트 제목, 키워드)",
    )
    node_type: NodeType = Field(
        default=NodeType.NOTE,
        description="노드의 종류. NodeType enum 참조.",
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="노드에 연결된 추가 메타데이터. (예: {'para_category': 'Projects', 'tags': ['AI']})",
    )
    position_x: Optional[float] = Field(
        default=None,
        description="시각화 화면에서의 X 좌표 (명시적 레이아웃 정보)",
    )
    position_y: Optional[float] = Field(
        default=None,
        description="시각화 화면에서의 Y 좌표 (명시적 레이아웃 정보)",
    )
    user_id_hash: Optional[str] = Field(
        default=None,
        description=(
            "이 노드의 소유자를 나타내는 해시된 사용자 ID. "
            "원본 user_id는 절대 저장/직렬화되지 않습니다 (PII 보호)."
        ),
    )

    @field_validator("user_id_hash")
    @classmethod
    def ensure_user_id_is_hashed(cls, v: Optional[str]) -> Optional[str]:
        """
        [보안 강화] user_id_hash 필드에 원본 ID가 실수로 주입되는 것을 차단합니다.
        오직 mask_pii_id()를 통과한 해시 문자열(12자리/64자리 Hex) 또는 INVALID_PII_SENTINEL만 허용합니다.
        """
        if v is None:
            return None
        
        if v == INVALID_PII_SENTINEL:
            return v
            
        # 정확히 소문자 a-f, 0-9 로 구성된 12자리(truncate) 또는 64자리(full sha256)만 허용
        if not USER_ID_HASH_PATTERN.fullmatch(v):
            raise ValueError(
                "PII 보안 경고: user_id_hash 필드에 안전하지 않은 값이 입력되었습니다. "
                "반드시 mask_pii_id(raw_user_id)를 통해 해싱된 값을 전달해야 합니다."
            )
        return v


class GraphEdge(BaseModel):
    """
    지식 그래프의 엣지(간선) 모델. [SSOT - v1]

    두 노드(source → target) 간의 방향 있는 관계를 표현합니다.
    """

    id: str = Field(
        ...,
        description="엣지의 고유 식별자. 충돌 방지를 위해 'e-{source_id}-{target_id}' 형식 권장.",
    )
    source: str = Field(
        ...,
        description="출발 노드의 id. GraphNode.id를 참조해야 합니다.",
    )
    target: str = Field(
        ...,
        description="도착 노드의 id. GraphNode.id를 참조해야 합니다.",
    )
    relationship_type: EdgeRelationshipType = Field(
        default=EdgeRelationshipType.EXPLICIT_LINK,
        description="두 노드 간의 관계 유형. EdgeRelationshipType enum 참조.",
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "엣지의 강도(유사도/중요도). 0.0(약한 연결) ~ 1.0(강한 연결). "
            "IMPLICIT_SEMANTIC 관계의 경우 LLM이 산출한 코사인 유사도를 사용."
        ),
    )


# ─────────────────────────────────────────
# API Response Models (v1)
# ─────────────────────────────────────────


class GraphDataResponse(BaseModel):
    """
    그래프 데이터 API 엔드포인트의 표준 응답 모델. [SSOT - v1]

    [OpenAPI 동기화]
    이 모델은 FastAPI의 response_model에 반드시 지정되어야 합니다.
    프론트엔드 타입 자동 생성의 근거가 되는 SSOT입니다.
    """

    nodes: list[GraphNode] = Field(
        default_factory=list,
        description="그래프를 구성하는 전체 노드 목록.",
    )
    edges: list[GraphEdge] = Field(
        default_factory=list,
        description="그래프를 구성하는 전체 엣지 목록.",
    )


# ─────────────────────────────────────────
# v1 Versioning Namespace (Breaking Change 대비)
# ─────────────────────────────────────────
#
# [버저닝 가이드]
# 향후 스키마에 Breaking Change가 발생할 경우 (예: 엣지 타입 다각화):
#
#   1. `backend/schemas/graph_v2.py` 파일을 신규 생성합니다.
#   2. 변경된 모델을 v2에 정의합니다 (이 파일의 v1 모델은 건드리지 않습니다).
#   3. 새 API 라우터를 `/api/v2/graph` 경로에 등록합니다.
#   4. `/api/v1/graph` 라우터는 Deprecation 헤더를 추가하여 일정 기간 유지합니다.
#   5. 프론트엔드 타입 자동 생성기를 v2 기준으로 재실행합니다.
#
# 이 네임스페이스 앨리어스는 현재 코드베이스에서
# "이 모델이 v1 계약임"을 명시적으로 드러내기 위한 임포트 편의 목적입니다.
#
GraphNodeV1 = GraphNode
GraphEdgeV1 = GraphEdge
GraphDataResponseV1 = GraphDataResponse

__all__ = [
    # Enums
    "NodeType",
    "EdgeRelationshipType",
    # v1 Core Models (SSOT)
    "GraphNode",
    "GraphEdge",
    "GraphDataResponse",
    # v1 Versioning Aliases
    "GraphNodeV1",
    "GraphEdgeV1",
    "GraphDataResponseV1",
]

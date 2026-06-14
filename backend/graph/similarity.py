# backend/graph/similarity.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 4-4 (3단계): 벡터 유사도 기반 연결 추천 쌍 발굴
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 설계 원칙:
#   - 순수 함수(Pure Function) 기반 — 부작용 없음, 단위 테스트 용이.
#   - 엔진 불가지론적 — 외부 임베딩 API에 의존하지 않음. 입력 벡터를 직접 받음.
#   - 하드코딩 금지 — 유사도 임계값은 환경 변수(LINK_SIMILARITY_THRESHOLD)에서 로드.
#   - PII 보안 — user_id 원문에 절대 접근하지 않음. node_id 접두어(8자리)만 로깅.
#   - 테넌트 격리 — 함수 인자로 이미 격리된 orphans/candidates를 받음.
#
# [LINK_SIMILARITY_THRESHOLD 환경 변수 규격]
#   타입  : float
#   기본값: 0.7  (코사인 유사도 0.7 이상인 쌍만 추천)
#   범위  : 0.0 ~ 1.0
#   파싱 오류 시: 기본값 폴백 + WARNING 로그
#   범위 초과 시: Clamp 처리 + WARNING 로그
#
# [MAX_RECOMMENDATIONS_PER_ORPHAN 환경 변수 규격]
#   타입  : int
#   기본값: 3  (고립 노드 1개당 최대 추천 쌍 수)
#   범위  : 1 ~ 50
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from __future__ import annotations

import logging
import os
from typing import Sequence

import numpy as np

from backend.schemas.graph import GraphNode, LinkRecommendation, OrphanNode

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# 환경 변수 상수 (하드코딩 금지)
# ─────────────────────────────────────────

_ENV_LINK_SIMILARITY_THRESHOLD = "LINK_SIMILARITY_THRESHOLD"
_DEFAULT_LINK_SIMILARITY_THRESHOLD: float = 0.7
_MIN_LINK_SIMILARITY_THRESHOLD: float = 0.0
_MAX_LINK_SIMILARITY_THRESHOLD: float = 1.0

_ENV_MAX_RECOMMENDATIONS_PER_ORPHAN = "MAX_RECOMMENDATIONS_PER_ORPHAN"
_DEFAULT_MAX_RECOMMENDATIONS_PER_ORPHAN: int = 3
_MIN_MAX_RECOMMENDATIONS_PER_ORPHAN: int = 1
_MAX_MAX_RECOMMENDATIONS_PER_ORPHAN: int = 50


# ─────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────


from typing import TypeVar

T = TypeVar("T", int, float)


def _clamp_core(value: T, min_val: T, max_val: T) -> T:
    """값을 [min_val, max_val] 범위 내로 Clamp한다."""
    return max(min_val, min(max_val, value))


def _clamp_float(
    value: float, min_val: float, max_val: float, source: str, label: str
) -> float:
    """float 값을 [min_val, max_val] 범위 내로 Clamp한다."""
    clamped = _clamp_core(value, min_val, max_val)
    if clamped != value:
        logger.warning(
            "[GRAPH][SIMILARITY] %s 기준 %s=%.4f 는 허용 범위 [%.4f, %.4f] 를 벗어났습니다. %.4f 로 Clamp 처리합니다.",
            source,
            label,
            value,
            min_val,
            max_val,
            clamped,
        )
    return clamped


def _clamp_int(value: int, min_val: int, max_val: int, source: str, label: str) -> int:
    """int 값을 [min_val, max_val] 범위 내로 Clamp한다."""
    clamped = _clamp_core(value, min_val, max_val)
    if clamped != value:
        logger.warning(
            "[GRAPH][SIMILARITY] %s 기준 %s=%d 는 허용 범위 [%d, %d] 를 벗어났습니다. %d 로 Clamp 처리합니다.",
            source,
            label,
            value,
            min_val,
            max_val,
            clamped,
        )
    return clamped


def get_link_similarity_threshold() -> float:
    """
    LINK_SIMILARITY_THRESHOLD 환경 변수에서 유사도 임계값을 로드한다.

    - 환경 변수 미설정 시: 기본값 반환
    - 파싱 실패 시: 기본값 폴백 + WARNING 로그
    - 범위(0.0~1.0) 초과 시: Clamp 처리 + WARNING 로그

    Returns:
        유효한 float 임계값 (항상 [0.0, 1.0] 범위 내 보장)
    """
    raw = os.environ.get(_ENV_LINK_SIMILARITY_THRESHOLD)
    if raw is None:
        return _DEFAULT_LINK_SIMILARITY_THRESHOLD

    try:
        value = float(raw.strip())
    except (ValueError, AttributeError):
        logger.warning(
            "[GRAPH][SIMILARITY] %s=%r 는 유효하지 않은 float입니다. 기본값 %.4f 로 폴백합니다.",
            _ENV_LINK_SIMILARITY_THRESHOLD,
            raw,
            _DEFAULT_LINK_SIMILARITY_THRESHOLD,
        )
        return _DEFAULT_LINK_SIMILARITY_THRESHOLD

    return _clamp_float(
        value,
        _MIN_LINK_SIMILARITY_THRESHOLD,
        _MAX_LINK_SIMILARITY_THRESHOLD,
        source=f"환경 변수({_ENV_LINK_SIMILARITY_THRESHOLD})",
        label="threshold",
    )


def get_max_recommendations_per_orphan() -> int:
    """
    MAX_RECOMMENDATIONS_PER_ORPHAN 환경 변수에서 최대 추천 수를 로드한다.

    Returns:
        유효한 int 값 (항상 [1, 50] 범위 내 보장)
    """
    raw = os.environ.get(_ENV_MAX_RECOMMENDATIONS_PER_ORPHAN)
    if raw is None:
        return _DEFAULT_MAX_RECOMMENDATIONS_PER_ORPHAN

    try:
        value = int(raw.strip())
    except (ValueError, AttributeError):
        logger.warning(
            "[GRAPH][SIMILARITY] %s=%r 는 유효하지 않은 int입니다. 기본값 %d 로 폴백합니다.",
            _ENV_MAX_RECOMMENDATIONS_PER_ORPHAN,
            raw,
            _DEFAULT_MAX_RECOMMENDATIONS_PER_ORPHAN,
        )
        return _DEFAULT_MAX_RECOMMENDATIONS_PER_ORPHAN

    return _clamp_int(
        value,
        _MIN_MAX_RECOMMENDATIONS_PER_ORPHAN,
        _MAX_MAX_RECOMMENDATIONS_PER_ORPHAN,
        source=f"환경 변수({_ENV_MAX_RECOMMENDATIONS_PER_ORPHAN})",
        label="max_recommendations",
    )


def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    두 벡터 간 코사인 유사도를 계산한다.

    Args:
        vec_a: 1D numpy float32 배열
        vec_b: 1D numpy float32 배열

    Returns:
        코사인 유사도 (float). 영벡터 입력 시 0.0 반환 (ZeroDivisionError 방지).
    """
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


# ─────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────


def _score_candidates_for_orphan(
    orphan_id: str,
    orphan_vec: np.ndarray,
    a_candidate_vecs: dict[str, np.ndarray],
    similarity_threshold: float,
) -> list[tuple[float, str]]:
    """고립 노드에 대해 유사도 임계값을 넘는 후보들을 평가하여 반환한다."""
    scored: list[tuple[float, str]] = []

    for candidate_id, candidate_vec in a_candidate_vecs.items():
        if candidate_id == orphan_id:
            continue

        if len(orphan_vec) != len(candidate_vec):
            logger.debug(
                "[GRAPH][SIMILARITY] 차원 불일치로 건너뜀: orphan(id=%s, dim=%d) != candidate(id=%s, dim=%d)",
                orphan_id[:8],
                len(orphan_vec),
                candidate_id[:8],
                len(candidate_vec),
            )
            continue

        sim = _cosine_similarity(orphan_vec, candidate_vec)
        if sim >= similarity_threshold:
            scored.append((sim, candidate_id))

    return scored


def find_link_recommendations(
    orphan_nodes: Sequence[OrphanNode],
    candidate_nodes: Sequence[GraphNode],
    orphan_embeddings: dict[str, list[float]],
    candidate_embeddings: dict[str, list[float]],
    similarity_threshold: float | None = None,
    max_per_orphan: int | None = None,
) -> list[LinkRecommendation]:
    """
    고립 노트와 기존 연결 노드 간 벡터 유사도를 측정하여, 잠재적 연관성이
    높은 연결 추천 쌍(LinkRecommendation)을 발굴하여 반환한다.

    [동작 방식]
    1. 각 고립 노드(orphan)의 임베딩과 후보 노드(candidate)의 임베딩 간 코사인 유사도를 계산한다.
    2. similarity_threshold 이상인 쌍만 추천 후보로 선정한다.
    3. 유사도 내림차순 정렬 후 고립 노드당 max_per_orphan개 이하로 반환한다.
    4. 고립 노드 자기 자신과의 쌍은 제외한다.

    [임베딩 입력 규약]
    - orphan_embeddings: {node_id: embedding_vector} 형태의 딕셔너리
    - candidate_embeddings: {node_id: embedding_vector} 형태의 딕셔너리
    - 임베딩이 없는 노드는 건너뛴다 (경고 로그 없이 조용히 제외).

    [테넌트 격리 계약]
    이 함수는 이미 테넌트 격리된 orphan_nodes/candidate_nodes를 입력으로 받는다.
    호출 측에서 hashed_user_id 기반으로 필터링된 데이터를 전달해야 한다.

    [PII 보안]
    로깅 시 node_id 원문이 아닌 8자리 접두어만 기록한다.

    Args:
        orphan_nodes: 고립 노드 목록 (테넌트 격리 완료)
        candidate_nodes: 연결 후보 노드 목록 (테넌트 격리 완료)
        orphan_embeddings: 고립 노드 ID → 임베딩 벡터 맵
        candidate_embeddings: 후보 노드 ID → 임베딩 벡터 맵
        similarity_threshold: 코사인 유사도 임계값 (None이면 환경 변수에서 로드)
        max_per_orphan: 고립 노드 1개당 최대 추천 수 (None이면 환경 변수에서 로드)

    Returns:
        LinkRecommendation 목록 — 유사도 내림차순 정렬.
        추천 쌍이 없으면 빈 리스트를 반환한다.
    """
    if similarity_threshold is None:
        similarity_threshold = get_link_similarity_threshold()
    else:
        similarity_threshold = _clamp_float(
            similarity_threshold,
            _MIN_LINK_SIMILARITY_THRESHOLD,
            _MAX_LINK_SIMILARITY_THRESHOLD,
            source="전달된 인자(similarity_threshold)",
            label="threshold",
        )

    if max_per_orphan is None:
        max_per_orphan = get_max_recommendations_per_orphan()
    else:
        max_per_orphan = _clamp_int(
            max_per_orphan,
            _MIN_MAX_RECOMMENDATIONS_PER_ORPHAN,
            _MAX_MAX_RECOMMENDATIONS_PER_ORPHAN,
            source="전달된 인자(max_per_orphan)",
            label="max_recommendations",
        )

    recommendations: list[LinkRecommendation] = []

    # 후보 노드 ID → GraphNode 빠른 조회 맵
    candidate_map: dict[str, GraphNode] = {n.id: n for n in candidate_nodes}

    # 사전에 후보/고립 임베딩을 np.ndarray로 변환하여 캐싱 (성능 최적화 및 대칭성 확보)
    a_candidate_vecs: dict[str, np.ndarray] = {
        cid: np.array(vec_raw, dtype=np.float32)
        for cid, vec_raw in candidate_embeddings.items()
    }
    a_orphan_vecs: dict[str, np.ndarray] = {
        oid: np.array(vec_raw, dtype=np.float32)
        for oid, vec_raw in orphan_embeddings.items()
    }

    # 데이터 일관성 검사: 임베딩 맵에 존재하지만 실제 노드 목록에 없는 경우 경고 (Data Inconsistency 방어)
    if missing_candidates := set(a_candidate_vecs.keys()) - set(candidate_map.keys()):
        logger.debug(
            "[GRAPH][SIMILARITY] candidate_embeddings에 %d개의 식별되지 않은 노드 ID가 있습니다. (무시됨)",
            len(missing_candidates),
        )
        for missing_id in missing_candidates:
            a_candidate_vecs.pop(missing_id, None)

    for orphan in orphan_nodes:
        # 임베딩 없는 고립 노드는 조용히 건너뜀
        if (orphan_vec := a_orphan_vecs.get(orphan.id)) is None:
            continue

        scored = _score_candidates_for_orphan(
            orphan_id=orphan.id,
            orphan_vec=orphan_vec,
            a_candidate_vecs=a_candidate_vecs,
            similarity_threshold=similarity_threshold,
        )

        # 유사도 내림차순 정렬
        scored.sort(key=lambda x: x[0], reverse=True)

        # max_per_orphan 개 이하로 제한하여 추천 생성
        for sim_score, candidate_id in scored[:max_per_orphan]:
            candidate_node = candidate_map.get(candidate_id)
            if candidate_node is None:
                # 후보 맵에 없는 ID는 건너뜀 (임베딩 맵과 노드 목록 불일치 방어)
                continue

            recommendations.append(
                LinkRecommendation(
                    orphan_node_id=orphan.id,
                    orphan_node_label=orphan.label,
                    candidate_node_id=candidate_id,
                    candidate_node_label=candidate_node.label,
                    similarity_score=round(sim_score, 6),
                    user_id_hash=orphan.user_id_hash,
                )
            )
            logger.debug(
                "[GRAPH][SIMILARITY] 연결 추천 발굴: orphan=%s, candidate=%s, score=%.4f",
                orphan.id[:8] if orphan.id else "<empty>",
                candidate_id[:8] if candidate_id else "<empty>",
                sim_score,
            )

    # 전체 결과를 유사도 내림차순으로 정렬
    recommendations.sort(key=lambda r: r.similarity_score, reverse=True)

    logger.info(
        "[GRAPH][SIMILARITY] 연결 추천 발굴 완료: 고립 노드=%d, 후보 노드=%d, 발굴된 추천 쌍=%d, 임계값=%.4f.",
        len(orphan_nodes),
        len(candidate_nodes),
        len(recommendations),
        similarity_threshold,
    )
    return recommendations


__all__ = [
    "find_link_recommendations",
    "get_link_similarity_threshold",
    "get_max_recommendations_per_orphan",
]

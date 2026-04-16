# backend/core/config_validator.py

"""
Global Configuration Validation Policy — v9.0 Phase 2 (Personalized RAG)
=========================================================================

장애 전파 범위(Blast Radius) 정책:

  [Global Hard Failure]
    필수 보안 설정(STORAGE_BASE_PATH, PBKDF2_ITERATIONS 등) 파싱 오류 시
    → 보안 오염 방지를 위해 SystemExit(1)으로 전체 애플리케이션 기동 즉시 중단.

  [Subsystem Hard Failure]
    선택적 부가 설정(FAISS_COMPACTION_*, TOPIC_CLUSTER_CACHE_TTL 등) 파싱 오류 시
    → Silent Fallback 금지. 해당 서브시스템만 비활성화하고 핵심 REST API는 유지.
    → HealthRegistry를 통해 DEGRADED 상태를 노출하여 상태 은폐 방지.

  [Graceful Fallback / Clamping]
    범위 기반 설정(AWS_WRAPPER_MAX_WORKERS 등) 값이 10 미만(< 10) 또는 100 초과(> 100)인 경우
    → 크래시 없이 안전 범위 내로 자율 보정(Clamp) + WARNING 로그 (환경변수명, 원래값, 보정값, 이유 포함).
    → 비정수/미설정 시 heuristic 기본값으로 폴백 + WARNING 로그.

이 모듈은 하나의 프로세스에서 한 번만 초기화됩니다 (bootstrap 단계).
민감 정보(시크릿, 키, 경로값)는 절대 로그에 기록하지 않습니다.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Callable, ClassVar, Dict

# 프로젝트 공통 유틸 재사용 — 중복 구현 금지
from backend.config import ConfigRange, _clamp

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 서브시스템 식별자
# ─────────────────────────────────────────────────────────────────────────────


class Subsystem(str, Enum):
    """서브시스템 식별자 (HealthRegistry 키로 사용)."""

    FAISS_COMPACTION = "faiss_compaction"
    TOPIC_CLUSTERING = "topic_clustering"
    HYBRID_SEARCH = "hybrid_search"
    PERSONALIZED_INDEX = "personalized_index"


# ─────────────────────────────────────────────────────────────────────────────
# 내부 파서 헬퍼 (모듈 내부 전용)
# ─────────────────────────────────────────────────────────────────────────────


def _parse_str_critical(env_key: str) -> str:
    """
    필수 문자열 환경 변수를 파싱한다.
    미설정 또는 빈 값이면 CRITICAL 로그 후 SystemExit(1) — Global Hard Failure.

    주의: 값 자체(경로, 식별자)는 보안상 로그에 기록하지 않는다.
    """
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        logger.critical(
            "[CONFIG][GLOBAL HARD FAILURE] '%s' is required but not set or empty. "
            "Application startup aborted to prevent security contamination.",
            env_key,
        )
        raise SystemExit(1)
    return raw


def _parse_int_critical(env_key: str, *, min_val: int | None = None) -> int:
    """
    필수 정수 환경 변수를 파싱한다.
    파싱 실패 또는 min_val 미달 시 CRITICAL 로그 후 SystemExit(1) — Global Hard Failure.
    """
    raw = os.environ.get(env_key)
    if raw is None:
        logger.critical(
            "[CONFIG][GLOBAL HARD FAILURE] '%s' is required but not set. "
            "Application startup aborted.",
            env_key,
        )
        raise SystemExit(1)

    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.critical(
            "[CONFIG][GLOBAL HARD FAILURE] '%s' must be an integer, got type=%s. "
            "Application startup aborted.",
            env_key,
            type(raw).__name__,
        )
        raise SystemExit(1)

    if min_val is not None and value < min_val:
        logger.critical(
            "[CONFIG][GLOBAL HARD FAILURE] '%s'=%d is below minimum required value %d. "
            "Application startup aborted.",
            env_key,
            value,
            min_val,
        )
        raise SystemExit(1)

    return value


def _parse_int_subsystem(
    env_key: str,
    *,
    default: int,
    range_: ConfigRange | None = None,
    subsystem: Subsystem,
) -> tuple[int, bool]:
    """
    선택적 정수 환경 변수를 파싱한다 (서브시스템 설정용).

    Returns:
        (value, ok): ok=False → 해당 서브시스템 비활성화 (Subsystem Hard Failure).
    """
    raw = os.environ.get(env_key)
    if raw is None:
        # 미설정은 기본값 사용 — 실패가 아님
        return default, True

    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.error(
            "[CONFIG][SUBSYSTEM HARD FAILURE][%s] '%s' must be an integer, got type=%s. "
            "Subsystem disabled. Core REST API remains operational.",
            subsystem.value,
            env_key,
            type(raw).__name__,
        )
        return default, False

    if range_ is not None:
        clamped = _clamp(value, range_)
        if clamped != value:
            logger.warning(
                "[CONFIG][CLAMP] '%s'=%d is out of range [%d, %d]; clamped to %d.",
                env_key,
                value,
                range_.min,
                range_.max,
                clamped,
            )
        return clamped, True

    return value, True


def _parse_float_subsystem(
    env_key: str,
    *,
    default: float,
    range_: ConfigRange | None = None,
    subsystem: Subsystem,
) -> tuple[float, bool]:
    """
    선택적 float 환경 변수를 파싱한다 (서브시스템 설정용).

    Returns:
        (value, ok): ok=False → 해당 서브시스템 비활성화 (Subsystem Hard Failure).
    """
    raw = os.environ.get(env_key)
    if raw is None:
        return default, True

    try:
        value = float(raw)
    except (ValueError, TypeError):
        logger.error(
            "[CONFIG][SUBSYSTEM HARD FAILURE][%s] '%s' must be a float, got type=%s. "
            "Subsystem disabled. Core REST API remains operational.",
            subsystem.value,
            env_key,
            type(raw).__name__,
        )
        return default, False

    if range_ is not None:
        clamped = _clamp(value, range_)
        if clamped != value:
            logger.warning(
                "[CONFIG][CLAMP] '%s'=%g is out of range [%g, %g]; clamped to %g.",
                env_key,
                value,
                range_.min,
                range_.max,
                clamped,
            )
        return clamped, True

    return value, True


def _parse_int_clamped(
    env_key: str,
    *,
    default_factory: Callable[[], int],
    range_: ConfigRange,
) -> int:
    """
    범위 기반 정수 환경 변수를 파싱한다 (Graceful Fallback / Clamping).

    - 미설정 또는 비정수: heuristic 기본값으로 폴백 + WARNING 로그
    - 값이 10 미만(< 10) 또는 100 초과(> 100): 경계로 보정 + WARNING 로그
      (10과 100은 유효한 경계값으로 보정 대상 제외)
    - 환경변수명·원래값·보정값·폴백 이유를 모두 WARNING 로그에 포함
    """
    default = default_factory()
    raw = os.environ.get(env_key)

    if raw is None:
        logger.warning(
            "[CONFIG][CLAMP] '%s' is not set; using heuristic default %d.",
            env_key,
            default,
        )
        return default

    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[CONFIG][CLAMP] '%s'=%r is not a valid integer; "
            "falling back to default %d provided by default_factory.",
            env_key,
            raw,
            default,
        )
        return default

    clamped = _clamp(value, range_)
    if clamped != value:
        reason = "범위 미만 보정" if value < range_.min else "범위 초과 보정"
        logger.warning(
            "[CONFIG][CLAMP] '%s'=%d is outside safe range [%d, %d]; "
            "clamped to %d (%s). "
            "Adjust '%s' to suppress this warning.",
            env_key,
            value,
            range_.min,
            range_.max,
            clamped,
            reason,
            env_key,
        )
    return clamped


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 통합 설정 클래스
# ─────────────────────────────────────────────────────────────────────────────


class PersonalizedRAGConfig:
    """
    v9.0 Phase 2 Personalized RAG 전용 검증 설정 클래스.

    사용법:
        cfg = PersonalizedRAGConfig.from_env()  # bootstrap 단계에서 1회 호출

    필수 환경 변수 (미설정 시 애플리케이션 기동 불가):
        STORAGE_BASE_PATH       - 사용자 데이터 루트 경로
        PBKDF2_ITERATIONS       - 키 파생 반복 횟수 (보안 최소값: 600,000)

    선택적 환경 변수 (파싱 오류 시 해당 서브시스템만 비활성화):
        FAISS_COMPACTION_VECTOR_THRESHOLD   (int, 기본: 500, 최소: 100)
        FAISS_COMPACTION_DELETE_RATIO       (float, 기본: 0.15, 범위: 0.0~1.0)
        TOPIC_CLUSTER_CACHE_TTL             (int, 초 단위, 기본: 3600)
        REDIS_FALLBACK_TTL_SECS             (int, 초 단위, 기본: 300)
        PERSONALIZED_INDEX_WEIGHT           (float, 기본: 0.6, 범위: 0.0~1.0)
        GLOBAL_INDEX_WEIGHT                 (float, 기본: 0.4, 범위: 0.0~1.0)

    범위 보정(Clamping) 환경 변수:
        AWS_WRAPPER_MAX_WORKERS (int, 기본: heuristic, 권장 범위: 10~100)
    """

    # 공유 ConfigRange 상수
    _WEIGHT_RANGE: ClassVar[ConfigRange] = ConfigRange(min=0.0, max=1.0)
    _FAISS_RATIO_RANGE: ClassVar[ConfigRange] = ConfigRange(min=0.0, max=1.0)
    _FAISS_THRESHOLD_RANGE: ClassVar[ConfigRange] = ConfigRange(min=100, max=100_000)
    _AWS_WORKERS_RANGE: ClassVar[ConfigRange] = ConfigRange(min=10, max=100)
    # Weight 합계 검증 허용 오차 (에: |sum - 1.0| ≤ 0.01이면 정상)
    _WEIGHT_SUM_TOLERANCE: ClassVar[float] = 0.01

    def __init__(
        self,
        *,
        # Critical
        storage_base_path: str,
        pbkdf2_iterations: int,
        # Optional subsystem
        faiss_compaction_vector_threshold: int,
        faiss_compaction_delete_ratio: float,
        topic_cluster_cache_ttl: int,
        redis_fallback_ttl_secs: int,
        personalized_index_weight: float,
        global_index_weight: float,
        # Clamped
        aws_wrapper_max_workers: int,
        # Subsystem health map
        subsystem_ok: Dict[str, bool],
    ) -> None:
        self.storage_base_path = storage_base_path
        self.pbkdf2_iterations = pbkdf2_iterations
        self.faiss_compaction_vector_threshold = faiss_compaction_vector_threshold
        self.faiss_compaction_delete_ratio = faiss_compaction_delete_ratio
        self.topic_cluster_cache_ttl = topic_cluster_cache_ttl
        self.redis_fallback_ttl_secs = redis_fallback_ttl_secs
        self.personalized_index_weight = personalized_index_weight
        self.global_index_weight = global_index_weight
        self.aws_wrapper_max_workers = aws_wrapper_max_workers
        # 서브시스템 가동 여부 맵 (True=활성, False=비활성)
        self.subsystem_ok: Dict[str, bool] = subsystem_ok

    @classmethod
    def from_env(cls) -> "PersonalizedRAGConfig":
        """
        환경 변수에서 설정을 파싱하여 PersonalizedRAGConfig 인스턴스를 반환한다.
        Critical 설정 파싱 실패 시 SystemExit(1) — Global Hard Failure.
        """
        # ── 1. Critical 설정 (Global Hard Failure) ────────────────────────
        storage_base_path = _parse_str_critical("STORAGE_BASE_PATH")
        pbkdf2_iterations = _parse_int_critical(
            "PBKDF2_ITERATIONS", min_val=600_000
        )

        # ── 2. 서브시스템 설정 (Subsystem Hard Failure) ───────────────────
        # subsystem_ok 키는 항상 str (Subsystem.value) 로 통일 — HealthRegistry 경계와 일치
        subsystem_ok: Dict[str, bool] = {}

        faiss_threshold, ok_ft = _parse_int_subsystem(
            "FAISS_COMPACTION_VECTOR_THRESHOLD",
            default=500,
            range_=cls._FAISS_THRESHOLD_RANGE,
            subsystem=Subsystem.FAISS_COMPACTION,
        )
        faiss_ratio, ok_fr = _parse_float_subsystem(
            "FAISS_COMPACTION_DELETE_RATIO",
            default=0.15,
            range_=cls._FAISS_RATIO_RANGE,
            subsystem=Subsystem.FAISS_COMPACTION,
        )
        # 두 설정 중 하나라도 실패하면 FAISS Compaction 서브시스템 비활성화
        subsystem_ok[Subsystem.FAISS_COMPACTION.value] = ok_ft and ok_fr

        topic_ttl, ok_ttl = _parse_int_subsystem(
            "TOPIC_CLUSTER_CACHE_TTL",
            default=3600,
            subsystem=Subsystem.TOPIC_CLUSTERING,
        )
        subsystem_ok[Subsystem.TOPIC_CLUSTERING.value] = ok_ttl

        p_weight, ok_pw = _parse_float_subsystem(
            "PERSONALIZED_INDEX_WEIGHT",
            default=0.6,
            range_=cls._WEIGHT_RANGE,
            subsystem=Subsystem.HYBRID_SEARCH,
        )
        g_weight, ok_gw = _parse_float_subsystem(
            "GLOBAL_INDEX_WEIGHT",
            default=0.4,
            range_=cls._WEIGHT_RANGE,
            subsystem=Subsystem.HYBRID_SEARCH,
        )
        subsystem_ok[Subsystem.HYBRID_SEARCH.value] = ok_pw and ok_gw

        # Weight 합계 검증: 운영자 오설정 조기 감지
        # 정규화는 Silent 수정으로 Zero Trust 원칙 위반 — WARNING 로그만 출력하고 원래 값 유지
        weight_sum = p_weight + g_weight
        if abs(weight_sum - 1.0) > cls._WEIGHT_SUM_TOLERANCE:
            logger.warning(
                "[CONFIG] PERSONALIZED_INDEX_WEIGHT=%.4f + GLOBAL_INDEX_WEIGHT=%.4f "
                "= %.4f (expected ~1.0, tolerance=±%.2f). "
                "Verify weights are configured correctly.",
                p_weight,
                g_weight,
                weight_sum,
                cls._WEIGHT_SUM_TOLERANCE,
            )

        # Redis 폴백 TTL은 인프라 설정이므로 Subsystem 비활성화 없이 기본값 적용
        redis_ttl, _ = _parse_int_subsystem(
            "REDIS_FALLBACK_TTL_SECS",
            default=300,
            subsystem=Subsystem.PERSONALIZED_INDEX,
        )

        # ── 3. 범위 보정(Clamping) 설정 ───────────────────────────────────
        def _cpu_heuristic() -> int:
            cpu = os.cpu_count() or 1
            return min(32, cpu + 4)

        aws_workers = _parse_int_clamped(
            "AWS_WRAPPER_MAX_WORKERS",
            default_factory=_cpu_heuristic,
            range_=cls._AWS_WORKERS_RANGE,
        )

        # ── 4. 비활성화된 서브시스템 운영 가시성 로깅 ────────────────────
        for sub, ok in subsystem_ok.items():
            if not ok:
                logger.error(
                    "[CONFIG][SUBSYSTEM DISABLED] '%s' subsystem is DISABLED due to "
                    "invalid configuration. Register via HealthRegistry for /health exposure.",
                    sub,
                )

        return cls(
            storage_base_path=storage_base_path,
            pbkdf2_iterations=pbkdf2_iterations,
            faiss_compaction_vector_threshold=faiss_threshold,
            faiss_compaction_delete_ratio=faiss_ratio,
            topic_cluster_cache_ttl=topic_ttl,
            redis_fallback_ttl_secs=redis_ttl,
            personalized_index_weight=p_weight,
            global_index_weight=g_weight,
            aws_wrapper_max_workers=aws_workers,
            subsystem_ok=subsystem_ok,
        )

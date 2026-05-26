# backend/core/config_validator.py

"""
Global Configuration Validation Policy — v9.0 Phase 2 (Personalized RAG) / Phase 3 (Realtime Streaming)
=========================================================================================================

장애 전파 범위(Blast Radius) 정책:

  [Global Hard Failure]
    필수 보안 설정(STORAGE_BASE_PATH, PBKDF2_ITERATIONS 등) 파싱 오류 시
    → 보안 오염 방지를 위해 SystemExit(1)으로 전체 애플리케이션 기동 즉시 중단.

  [Subsystem Hard Failure]
    선택적 부가 설정(FAISS_COMPACTION_*, TOPIC_CLUSTER_CACHE_TTL,
    SSE_KEEPALIVE_INTERVAL_SECS 등) 파싱 오류 시
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
from typing import Callable, ClassVar, Dict, Literal, Mapping

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
    REALTIME_STREAMING = "realtime_streaming"  # Phase 3: 실시간 스트리밍 서브시스템
    GRAPH_ENGINE = "graph_engine"  # Phase 4: 지식 그래프 엔진 서브시스템


class SubsystemHealthState(str, Enum):
    """서브시스템 상태 식별자 (로깅 및 가시성 목적)."""

    DISABLED = "DISABLED"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


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
    except (ValueError, TypeError) as exc:
        logger.critical(
            "[CONFIG][GLOBAL HARD FAILURE] '%s' must be an integer, got type=%s. "
            "Application startup aborted.",
            env_key,
            type(raw).__name__,
        )
        raise SystemExit(1) from exc

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


def _log_clamp_warning(
    env_key: str,
    original: int | float,
    clamped: int | float,
    range_: ConfigRange,
) -> None:
    """Clamping 로그 일관화 헬퍼."""
    reason = "범위 미만 보정" if original < range_.min else "범위 초과 보정"
    logger.warning(
        "[CONFIG][CLAMP] '%s'=%g is outside safe range [%g, %g]; "
        "clamped to %g (%s). "
        "Adjust '%s' to suppress this warning.",
        env_key,
        original,
        range_.min,
        range_.max,
        clamped,
        reason,
        env_key,
    )


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
            _log_clamp_warning(env_key, value, clamped, range_)
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
            _log_clamp_warning(env_key, value, clamped, range_)
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
        _log_clamp_warning(env_key, value, clamped, range_)
    return clamped


def _parse_float_clamped(
    env_key: str,
    *,
    default: float,
    range_: ConfigRange,
) -> float:
    """
    범위 기반 float 환경 변수를 파싱한다 (Graceful Fallback / Clamping).
    """
    raw = os.environ.get(env_key)

    if raw is None:
        return default

    try:
        value = float(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[CONFIG][CLAMP] '%s'=%r is not a valid float; "
            "falling back to default %g.",
            env_key,
            raw,
            default,
        )
        return default

    clamped = _clamp(value, range_)
    if clamped != value:
        _log_clamp_warning(env_key, value, clamped, range_)
    return clamped


def _log_subsystem_state(
    subsystem_ok: Mapping[Subsystem, bool],
    *,
    state_label: SubsystemHealthState = SubsystemHealthState.DISABLED,
) -> None:
    """서브시스템 상태(비활성/저하/비정상) 운영 가시성 로깅 헬퍼.

    Args:
        subsystem_ok: 서브시스템별 상태 플래그 (True: 정상, False: 비정상/비활성/저하).
        state_label: 서브시스템 상태 레이블. 각 설정 클래스의 도메인 의미(비활성/저하 등)에 맞게 호출부에서 지정.
    """
    for sub, ok in subsystem_ok.items():
        if not ok:
            # sub는 Subsystem 타입임이 보장되므로, 명시적으로 .value를 호출하여 str로 변환
            sub_name: str = sub.value
            
            # 상태에 따른 동적 로그 레벨 할당
            # DEGRADED, UNHEALTHY는 서비스가 유지되므로 WARNING, 
            # DISABLED는 일부 기능이 정지되므로 ERROR 레벨 할당
            log_level = logging.WARNING if state_label in (SubsystemHealthState.DEGRADED, SubsystemHealthState.UNHEALTHY) else logging.ERROR
            
            logger.log(
                log_level,
                "[CONFIG][SUBSYSTEM %s] '%s' subsystem is %s due to invalid "
                "configuration. Register via HealthRegistry for /health exposure.",
                state_label.value,
                sub_name,
                state_label.value,
            )


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

    _DEFAULT_WEIGHT_SUM_TOLERANCE: ClassVar[float] = 0.01
    _WEIGHT_SUM_TOLERANCE_RANGE: ClassVar[ConfigRange] = ConfigRange(min=0.0, max=1.0)

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
        subsystem_ok: Dict[Subsystem, bool],
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
        self.subsystem_ok: Dict[Subsystem, bool] = subsystem_ok

    @classmethod
    def from_env(cls) -> "PersonalizedRAGConfig":
        """
        환경 변수에서 설정을 파싱하여 PersonalizedRAGConfig 인스턴스를 반환한다.
        Critical 설정 파싱 실패 시 SystemExit(1) — Global Hard Failure.
        """
        # ── 1. Critical 설정 (Global Hard Failure) ────────────────────────
        storage_base_path = _parse_str_critical("STORAGE_BASE_PATH")
        pbkdf2_iterations = _parse_int_critical("PBKDF2_ITERATIONS", min_val=600_000)

        # ── 2. 서브시스템 설정 (Subsystem Hard Failure) ───────────────────
        # subsystem_ok 키는 항상 Subsystem Enum으로 통일 — 타입 안전성 보장
        subsystem_ok: Dict[Subsystem, bool] = {}

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
        subsystem_ok[Subsystem.FAISS_COMPACTION] = ok_ft and ok_fr

        topic_ttl, ok_ttl = _parse_int_subsystem(
            "TOPIC_CLUSTER_CACHE_TTL",
            default=3600,
            subsystem=Subsystem.TOPIC_CLUSTERING,
        )
        subsystem_ok[Subsystem.TOPIC_CLUSTERING] = ok_ttl

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
        subsystem_ok[Subsystem.HYBRID_SEARCH] = ok_pw and ok_gw

        tolerance = _parse_float_clamped(
            "WEIGHT_SUM_TOLERANCE",
            default=cls._DEFAULT_WEIGHT_SUM_TOLERANCE,
            range_=cls._WEIGHT_SUM_TOLERANCE_RANGE,
        )

        # Weight 합계 검증: 운영자 오설정 조기 감지
        # 정규화는 Silent 수정으로 Zero Trust 원칙 위반 — WARNING 로그만 출력하고 원래 값 유지
        weight_sum = p_weight + g_weight
        if abs(weight_sum - 1.0) > tolerance:
            logger.warning(
                "[CONFIG] PERSONALIZED_INDEX_WEIGHT=%.4f + GLOBAL_INDEX_WEIGHT=%.4f "
                "= %.4f (expected ~1.0, tolerance=±%.2f). "
                "Verify weights are configured correctly.",
                p_weight,
                g_weight,
                weight_sum,
                tolerance,
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

        # ── 4. 서브시스템 상태(비활성/저하/비정상) 운영 가시성 로깅 ──────────
        _log_subsystem_state(subsystem_ok)

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


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 스트리밍 설정 검증 클래스
# ─────────────────────────────────────────────────────────────────────────────


class RealtimeStreamingConfig:
    """
    v9.0 Phase 3 Realtime Streaming 전용 검증 설정 클래스.

    사용법:
        cfg = RealtimeStreamingConfig.from_env()  # bootstrap 단계에서 1회 호출

    책임 (3-0/3-5 SSOT 정책 준수):
        - StreamingConfig(backend/core/config/streaming.py)에서 정의된
          스키마와 기본값을 바탕으로 OS 환경 변수를 로드한다.
        - 바운더리 체크(Clamping) 및 유효성 검증을 중앙에서 강제한다.
        - 파싱 오류 시 REALTIME_STREAMING 서브시스템만 DEGRADED 처리하고
          기존 비스트리밍 엔드포인트 생존성을 유지한다 (Subsystem Hard Failure).

    검증 시점 (Fail-Fast):
        사용자 요청 시점(Request-time)이 아닌 애플리케이션 시작(Bootstrap/Startup)
        시점에 즉각 수행되어야 한다.

    선택적 환경 변수 (파싱 오류 시 해당 서브시스템만 비활성화):
        SSE_KEEPALIVE_INTERVAL_SECS  (int, 기본: 15, 범위: 5~60)
        STREAM_BUFFER_MAX_SIZE       (int, 기본: 100, 범위: 10~1000)
        STREAM_TIMEOUT_SECS          (int, 기본: 120, 범위: 30~600)
        LANGGRAPH_STREAM_VERSION     (str, 기본: "v2", 허용: "v1"/"v2")

    보안 원칙:
        민감 정보(사용자 ID, 토큰 등)는 절대 로그에 기록하지 않는다.
    """

    def __init__(
        self,
        *,
        keepalive_interval_secs: int,
        buffer_max_size: int,
        timeout_secs: int,
        stream_version: str,
        subsystem_ok: Dict[Subsystem, bool],
    ) -> None:
        self.keepalive_interval_secs = keepalive_interval_secs
        self.buffer_max_size = buffer_max_size
        self.timeout_secs = timeout_secs
        self.stream_version = stream_version
        # 서브시스템 가동 여부 맵: Enum 키로 내부 관리, 경계에서만 .value 변환
        self.subsystem_ok: Dict[Subsystem, bool] = subsystem_ok

    @classmethod
    def from_env(cls) -> "RealtimeStreamingConfig":
        """
        환경 변수에서 스트리밍 설정을 파싱하여 RealtimeStreamingConfig 인스턴스를 반환한다.
        파싱 오류 시 REALTIME_STREAMING 서브시스템 비활성화 — Subsystem Hard Failure.
        전체 서버 부팅을 중단하지 않으며 기존 비스트리밍 API는 정상 유지된다.
        """
        # 공개 상수 별칭을 통해 임포트 (밑줄 접두 내부 상수 직접 참조 금지)
        from backend.core.config.streaming import (
            STREAMING_DEFAULT_KEEPALIVE_INTERVAL_SECS,
            STREAMING_DEFAULT_BUFFER_MAX_SIZE,
            STREAMING_DEFAULT_TIMEOUT_SECS,
            STREAMING_DEFAULT_STREAM_VERSION,
            STREAMING_KEEPALIVE_INTERVAL_RANGE,
            STREAMING_BUFFER_MAX_SIZE_RANGE,
            STREAMING_TIMEOUT_RANGE,
            STREAMING_VALID_STREAM_VERSIONS,
            STREAMING_ENV_KEEPALIVE_INTERVAL,
            STREAMING_ENV_BUFFER_MAX_SIZE,
            STREAMING_ENV_TIMEOUT,
            STREAMING_ENV_STREAM_VERSION,
        )

        # Dict[Subsystem, bool]: Enum 키로 내부 타입 안전성 확보
        subsystem_ok: Dict[Subsystem, bool] = {}

        # ── 서브시스템 설정 (Subsystem Hard Failure) ──────────────────────
        keepalive, ok_ka = _parse_int_subsystem(
            STREAMING_ENV_KEEPALIVE_INTERVAL,
            default=STREAMING_DEFAULT_KEEPALIVE_INTERVAL_SECS,
            range_=STREAMING_KEEPALIVE_INTERVAL_RANGE,
            subsystem=Subsystem.REALTIME_STREAMING,
        )
        buffer_size, ok_buf = _parse_int_subsystem(
            STREAMING_ENV_BUFFER_MAX_SIZE,
            default=STREAMING_DEFAULT_BUFFER_MAX_SIZE,
            range_=STREAMING_BUFFER_MAX_SIZE_RANGE,
            subsystem=Subsystem.REALTIME_STREAMING,
        )
        timeout, ok_to = _parse_int_subsystem(
            STREAMING_ENV_TIMEOUT,
            default=STREAMING_DEFAULT_TIMEOUT_SECS,
            range_=STREAMING_TIMEOUT_RANGE,
            subsystem=Subsystem.REALTIME_STREAMING,
        )

        # 문자열 열거형 검증 (허용 버전 이외 값 → 기본값 폴백)
        # ENV key 존재 여부를 먼저 확인하여 기본값에 불필요한 .strip() 방지
        if STREAMING_ENV_STREAM_VERSION in os.environ:
            raw_version = os.environ[STREAMING_ENV_STREAM_VERSION].strip()
        else:
            raw_version = STREAMING_DEFAULT_STREAM_VERSION

        if raw_version not in STREAMING_VALID_STREAM_VERSIONS:
            logger.error(
                "[CONFIG][SUBSYSTEM HARD FAILURE][%s] '%s'=%r is not a valid version. "
                "Allowed: %s. Subsystem disabled. Core REST API remains operational.",
                Subsystem.REALTIME_STREAMING.value,
                STREAMING_ENV_STREAM_VERSION,
                raw_version,
                STREAMING_VALID_STREAM_VERSIONS,
            )
            stream_version = STREAMING_DEFAULT_STREAM_VERSION
            ok_ver = False
        else:
            stream_version = raw_version
            ok_ver = True

        # 하나라도 실패하면 REALTIME_STREAMING 서브시스템 비활성화
        subsystem_ok[Subsystem.REALTIME_STREAMING] = (
            ok_ka and ok_buf and ok_to and ok_ver
        )

        # ── 서브시스템 상태(비활성/저하/비정상) 운영 가시성 로깅 (경계에서 .value 변환) ──
        _log_subsystem_state(subsystem_ok, state_label=SubsystemHealthState.DEGRADED)

        return cls(
            keepalive_interval_secs=keepalive,
            buffer_max_size=buffer_size,
            timeout_secs=timeout,
            stream_version=stream_version,
            subsystem_ok=subsystem_ok,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 지식 그래프 설정 검증 클래스
# ─────────────────────────────────────────────────────────────────────────────


class GraphEngineConfig:
    """
    v9.0 Phase 4 Knowledge Graph 전용 검증 설정 클래스.

    사용법:
        cfg = GraphEngineConfig.from_env()  # bootstrap 단계에서 1회 호출

    책임 (4-5 SSOT 정책 준수):
        - backend.core.config.graph 모듈에서 정의된 상수(ENV 키·기본값·범위)를
          참조하여 OS 환경 변수를 로드한다. (하드코딩 절대 금지)
        - 정수 범위 이탈 시 경계값으로 Clamping 보정 + WARNING 구조화 로그 출력.
        - GRAPH_DB_URL 미설정·빈 값 시 networkx 인메모리 폴백 (INFO 로그, 오류 아님).
        - 정수 파싱 자체가 불가한 경우(비정수 값) GRAPH_ENGINE 서브시스템만
          DEGRADED 처리 (Subsystem Fail-fast). 전체 서버 부팅은 유지.

    검증 대상 환경 변수 (모두 GraphConfig SSOT 상수로 참조):
        GRAPH_MAX_TRAVERSAL_DEPTH             (int, 기본: 3,     범위: 1~5)
        NEXT_PUBLIC_MAX_GRAPH_NODES           (int, 기본: 500,   범위: 50~2000)
        GRAPH_DB_URL                          (str, 기본: "",    빈 값 시 networkx Fallback)
        GRAPH_MIGRATION_NODE_THRESHOLD        (int, 기본: 10000, 범위: 5000~50000)
        GRAPH_MIGRATION_CONCURRENCY_THRESHOLD (int, 기본: 10,    범위: 5~100)

    보안 원칙:
        DB 연결 문자열(GRAPH_DB_URL) 값 자체는 절대 로그에 기록하지 않는다.
    """

    def __init__(
        self,
        *,
        max_traversal_depth: int,
        max_graph_nodes: int,
        db_url: str,
        migration_node_threshold: int,
        migration_concurrency_threshold: int,
        subsystem_ok: Dict[Subsystem, bool],
    ) -> None:
        self.max_traversal_depth = max_traversal_depth
        self.max_graph_nodes = max_graph_nodes
        # 보안: DB URL은 인스턴스 변수로만 보관, 절대 로그 출력 금지
        self.db_url = db_url
        self.migration_node_threshold = migration_node_threshold
        self.migration_concurrency_threshold = migration_concurrency_threshold
        # 서브시스템 가동 여부 맵 (True=활성, False=DEGRADED)
        self.subsystem_ok: Dict[Subsystem, bool] = subsystem_ok

    @classmethod
    def from_env(cls) -> "GraphEngineConfig":
        """
        환경 변수에서 그래프 설정을 파싱하여 GraphEngineConfig 인스턴스를 반환한다.

        - 정수 파싱 실패(비정수 값): GRAPH_ENGINE 서브시스템 DEGRADED — Subsystem Hard Failure.
        - 정수 범위 이탈: Clamping 보정 + WARNING 로그 — Graceful Fallback.
        - GRAPH_DB_URL 미설정·빈 값: networkx 인메모리 폴백 — INFO 로그 (오류 아님).
        - 전체 서버 부팅은 어떠한 경우에도 중단하지 않는다.
        """
        # SSOT: 모든 상수를 graph.py에서 import — 하드코딩 금지
        from backend.core.config.graph import (
            DEFAULT_MAX_TRAVERSAL_DEPTH,
            DEFAULT_MAX_GRAPH_NODES,
            DEFAULT_DB_URL,
            DEFAULT_MIGRATION_NODE_THRESHOLD,
            DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD,
            ENV_DB_URL,
            ENV_MAX_GRAPH_NODES,
            ENV_MAX_TRAVERSAL_DEPTH,
            ENV_MIGRATION_CONCURRENCY_THRESHOLD,
            ENV_MIGRATION_NODE_THRESHOLD,
            MAX_GRAPH_NODES_RANGE,
            MAX_TRAVERSAL_DEPTH_RANGE,
            MIGRATION_CONCURRENCY_THRESHOLD_RANGE,
            MIGRATION_NODE_THRESHOLD_RANGE,
        )

        # subsystem_ok 키는 항상 Subsystem Enum으로 통일 — 타입 안전성 보장
        subsystem_ok: Dict[Subsystem, bool] = {}

        # ── 정수 설정: Clamp + WARNING (범위 이탈) / DEGRADED (파싱 불가) ─────
        max_depth, ok_depth = _parse_int_subsystem(
            ENV_MAX_TRAVERSAL_DEPTH,
            default=DEFAULT_MAX_TRAVERSAL_DEPTH,
            range_=MAX_TRAVERSAL_DEPTH_RANGE,
            subsystem=Subsystem.GRAPH_ENGINE,
        )
        max_nodes, ok_nodes = _parse_int_subsystem(
            ENV_MAX_GRAPH_NODES,
            default=DEFAULT_MAX_GRAPH_NODES,
            range_=MAX_GRAPH_NODES_RANGE,
            subsystem=Subsystem.GRAPH_ENGINE,
        )
        migration_node, ok_mn = _parse_int_subsystem(
            ENV_MIGRATION_NODE_THRESHOLD,
            default=DEFAULT_MIGRATION_NODE_THRESHOLD,
            range_=MIGRATION_NODE_THRESHOLD_RANGE,
            subsystem=Subsystem.GRAPH_ENGINE,
        )
        migration_concurrency, ok_mc = _parse_int_subsystem(
            ENV_MIGRATION_CONCURRENCY_THRESHOLD,
            default=DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD,
            range_=MIGRATION_CONCURRENCY_THRESHOLD_RANGE,
            subsystem=Subsystem.GRAPH_ENGINE,
        )

        # ── GRAPH_DB_URL: 빈 값 = networkx 폴백 (오류 아님) ───────────────
        # 보안 원칙: DB URL 값 자체는 절대 로그에 기록하지 않음
        raw_db_url = os.environ.get(ENV_DB_URL, DEFAULT_DB_URL).strip()
        if not raw_db_url:
            logger.info(
                "[CONFIG][GRAPH] '%s' is not set or empty; "
                "using networkx in-memory fallback (no external graph DB).",
                ENV_DB_URL,
            )
        db_url = raw_db_url

        # ── 서브시스템 건강 판정: 하나라도 파싱 실패 시 DEGRADED ──────────
        # GRAPH_DB_URL 파싱 실패는 서브시스템 비활성화 조건에 포함하지 않음
        # (빈 값은 유효한 상태이므로)
        subsystem_ok[Subsystem.GRAPH_ENGINE] = (
            ok_depth and ok_nodes and ok_mn and ok_mc
        )

        # ── 서브시스템 상태(비활성/저하/비정상) 운영 가시성 로깅 ───────────────────────
        _log_subsystem_state(subsystem_ok, state_label=SubsystemHealthState.DEGRADED)

        return cls(
            max_traversal_depth=max_depth,
            max_graph_nodes=max_nodes,
            db_url=db_url,
            migration_node_threshold=migration_node,
            migration_concurrency_threshold=migration_concurrency,
            subsystem_ok=subsystem_ok,
        )

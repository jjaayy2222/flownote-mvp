# backend/core/config_validator.py

"""
Global Configuration Validation Policy - v9.0 Phase 2 (Personalized RAG) / Phase 3 (Realtime Streaming)
=========================================================================================================

Blast Radius Policy:

[Global Hard Failure]
On parsing failure for required security settings (STORAGE_BASE_PATH, PBKDF2_ITERATIONS, etc.),
the entire application exits immediately via SystemExit(1) to prevent security contamination.

[Subsystem Hard Failure]
On parsing failure for optional subsystem settings
(FAISS_COMPACTION_*, TOPIC_CLUSTER_CACHE_TTL, SSE_KEEPALIVE_INTERVAL_SECS, etc.),
silent fallback is prohibited. Only the affected subsystem is disabled; the core REST API remains operational.
The DEGRADED status is exposed via HealthRegistry to prevent status concealment.

[Graceful Fallback / Clamping]
For range-based settings (AWS_WRAPPER_MAX_WORKERS, etc.), values below the minimum or above the maximum
are autonomously clamped to the safe range with a WARNING log
(env var name, original value, clamped value, and reason are all included).
On non-integer or unset values, falls back to a heuristic default with a WARNING log.

This module is initialized once per process during the bootstrap phase.
Sensitive data (secrets, keys, paths) must never be written to logs.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Callable, ClassVar, Dict, Mapping

# Reuse shared project utilities — do not re-implement
from backend.config import ConfigRange, _clamp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subsystem identifiers
# ---------------------------------------------------------------------------


class Subsystem(str, Enum):
    """Subsystem identifiers used as HealthRegistry keys.

    Each member's str value is used directly as the HealthRegistry registration key.
    When adding a new subsystem, define a member here and include the key
    in the corresponding _log_subsystem_state call site.
    """

    FAISS_COMPACTION = "faiss_compaction"  # Phase 2: FAISS vector index compaction
    TOPIC_CLUSTERING = "topic_clustering"  # Phase 2: Topic clustering cache
    HYBRID_SEARCH = "hybrid_search"  # Phase 2: Personalized/global hybrid search
    PERSONALIZED_INDEX = "personalized_index"  # Phase 2: Per-user personalized index
    REALTIME_STREAMING = "realtime_streaming"  # Phase 3: Realtime streaming subsystem
    GRAPH_ENGINE = "graph_engine"  # Phase 4: Knowledge graph engine subsystem


class SubsystemHealthState(str, Enum):
    """Subsystem health state identifiers and log-level SSOT (logging/observability).

    Each member defines both a label and a log_level together.
    When adding a new state, assign a standard logging-module constant in __new__.
    log_level is exposed as a read-only property only.
    """

    # For this enum only — only standard logging module constants are allowed (no hardcoded integers).
    # Using dunder (__) names prevents Enum from treating this as a member,
    # making it behave as a regular ClassVar.
    __ALLOWED_LOG_LEVELS__: ClassVar[frozenset[int]] = frozenset(
        {
            logging.NOTSET,
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        }
    )

    DISABLED = ("DISABLED", logging.ERROR)
    DEGRADED = ("DEGRADED", logging.WARNING)

    _log_level: int

    def __new__(cls, label: str, log_level: int) -> "SubsystemHealthState":
        if not isinstance(log_level, int):
            raise ValueError(
                f"[CONFIG][SUBSYSTEM] SubsystemHealthState.{label!r} requires "
                f"log_level to be int, got {type(log_level).__name__}."
            )
        if log_level not in cls.__ALLOWED_LOG_LEVELS__:
            raise ValueError(
                f"[CONFIG][SUBSYSTEM] SubsystemHealthState.{label!r} has invalid "
                f"log_level={log_level}. Use a standard logging.* constant."
            )
        obj = str.__new__(cls, label)
        obj._value_ = label
        obj._log_level = log_level
        return obj

    @property
    def log_level(self) -> int:
        """Standard logging level corresponding to this state (read-only)."""
        return self._log_level


# ---------------------------------------------------------------------------
# Internal parser helpers (module-private)
# ---------------------------------------------------------------------------


def _parse_str_critical(env_key: str) -> str:
    """Parse a required string environment variable.

    If the variable is not set or is empty, logs CRITICAL and exits immediately
    via SystemExit(1). (Global Hard Failure — see module-level Blast Radius Policy.)

    Reads the OS environment variable specified by env_key, strips whitespace,
    and returns the non-empty string value. The value itself (path, identifier, etc.)
    is never written to logs per the security policy.
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
    """Parse a required integer environment variable.

    If parsing fails or the value is below min_val, logs CRITICAL and exits
    via SystemExit(1). (Global Hard Failure — see module-level Blast Radius Policy.)

    Reads the environment variable specified by env_key and converts it to int.
    If min_val is provided, performs a minimum-value check; otherwise skips it.
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
    """Internal helper that emits a structured WARNING log when clamping occurs.

    Logs env var name, original value, clamped value, allowed range, and reason
    in a consistent format so operators can identify misconfigured settings immediately.

    Args:
        env_key:  Name of the environment variable being clamped.
        original: The original value before clamping.
        clamped:  The value after clamping to the safe range.
        range_:   The ConfigRange instance defining the allowed min/max bounds.
    """
    reason = (
        "below-range correction" if original < range_.min else "above-range correction"
    )
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
    """Parse an optional integer environment variable for a subsystem setting.

    On parse failure, disables only the affected subsystem instead of terminating
    the entire application. (Subsystem Hard Failure — see module-level Blast Radius Policy.)
    If range_ is provided, applies clamping and emits a WARNING log.

    Args:
        env_key:   Name of the OS environment variable.
        default:   Fallback value when the variable is not set.
        range_:    Allowed range as a ConfigRange instance (None to skip range check).
        subsystem: Subsystem identifier for log context.

    Returns:
        A tuple[int, bool] where the bool is True on success and False on parse failure.
    """
    raw = os.environ.get(env_key)
    if raw is None:
        # Not set — use default; this is not a failure.
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
    """Parse an optional float environment variable for a subsystem setting.

    On parse failure, disables only the affected subsystem instead of terminating
    the entire application. (Subsystem Hard Failure — see module-level Blast Radius Policy.)
    If range_ is provided, applies clamping and emits a WARNING log.

    Args:
        env_key:   Name of the OS environment variable.
        default:   Fallback value when the variable is not set.
        range_:    Allowed range as a ConfigRange instance (None to skip range check).
        subsystem: Subsystem identifier for log context.

    Returns:
        A tuple[float, bool] where the bool is True on success and False on parse failure.
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
    """Parse a range-based integer environment variable with Graceful Fallback/Clamping.

    Autonomously clamps the value to the safe range without disabling any subsystem.
    All corrections and fallback reasons are recorded in a structured WARNING log.
    (Graceful Fallback — see module-level Blast Radius Policy.)

    Behavior rules:
    - If unset or non-integer: falls back to default_factory() result with a WARNING log.
    - If out of range: clamps to the boundary value with a WARNING log.
      (Boundary values themselves are not subject to further clamping.)
    - Env var name, original value, clamped value, and fallback reason are all
      included in the WARNING log.
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
    """Parse a range-based float environment variable with Graceful Fallback/Clamping.

    Autonomously clamps the value to the safe range without disabling any subsystem.
    (Graceful Fallback — see module-level Blast Radius Policy.)
    If the variable is not set, returns the default silently without logging.
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
    """Observability logging helper for abnormal subsystem states (DISABLED, DEGRADED).

    Supported state types:
    - DISABLED: subsystem deactivated due to parse failure, etc. (ERROR-level log).
    - DEGRADED: subsystem partially degraded after clamping (WARNING-level log).

    Args:
        subsystem_ok: Mapping of per-subsystem health flags (True=active, False=inactive).
        state_label:  Health state label to assign to failed subsystems.
    """
    log_level = state_label.log_level

    for sub, ok in subsystem_ok.items():
        if not ok:
            # sub is guaranteed to be Subsystem type; call .value explicitly for str conversion
            sub_name: str = sub.value

            logger.log(
                log_level,
                "[CONFIG][SUBSYSTEM %s] '%s' subsystem is %s due to invalid "
                "configuration. Register via HealthRegistry for /health exposure.",
                state_label.value,
                sub_name,
                state_label.value,
            )


# ---------------------------------------------------------------------------
# Phase 2 integrated configuration class
# ---------------------------------------------------------------------------


class PersonalizedRAGConfig:
    """Configuration validation class for v9.0 Phase 2 Personalized RAG.

    Usage:
        cfg = PersonalizedRAGConfig.from_env()  # call once during bootstrap

    Required environment variables (application cannot start if unset):
        STORAGE_BASE_PATH       - Root path for user data storage
        PBKDF2_ITERATIONS       - Key derivation iteration count (security minimum: 600,000)

    Optional environment variables (parse failure disables only the affected subsystem):
        FAISS_COMPACTION_VECTOR_THRESHOLD   (int, default: 500, min: 100)
        FAISS_COMPACTION_DELETE_RATIO       (float, default: 0.15, range: 0.0-1.0)
        TOPIC_CLUSTER_CACHE_TTL             (int, seconds, default: 3600)
        REDIS_FALLBACK_TTL_SECS             (int, seconds, default: 300)
        PERSONALIZED_INDEX_WEIGHT           (float, default: 0.6, range: 0.0-1.0)
        GLOBAL_INDEX_WEIGHT                 (float, default: 0.4, range: 0.0-1.0)

    Range-clamped environment variables:
        AWS_WRAPPER_MAX_WORKERS (int, default: heuristic, recommended range: 10-100)
    """

    # Shared ConfigRange constants
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
        """Initialize a PersonalizedRAGConfig instance.

        Use the :meth:`from_env` class method instead of calling this directly.
        All arguments are keyword-only.

        Args:
            storage_base_path:                  Root path for user data (STORAGE_BASE_PATH).
            pbkdf2_iterations:                  Key derivation iteration count (PBKDF2_ITERATIONS).
            faiss_compaction_vector_threshold:  FAISS compaction trigger vector count threshold
                                                (FAISS_COMPACTION_VECTOR_THRESHOLD).
            faiss_compaction_delete_ratio:      FAISS compaction delete ratio 0.0-1.0
                                                (FAISS_COMPACTION_DELETE_RATIO).
            topic_cluster_cache_ttl:            Topic cluster cache TTL in seconds
                                                (TOPIC_CLUSTER_CACHE_TTL).
            redis_fallback_ttl_secs:            Redis fallback TTL in seconds
                                                (REDIS_FALLBACK_TTL_SECS).
            personalized_index_weight:          Personalized index weight 0.0-1.0
                                                (PERSONALIZED_INDEX_WEIGHT).
            global_index_weight:                Global index weight 0.0-1.0
                                                (GLOBAL_INDEX_WEIGHT).
            aws_wrapper_max_workers:            Max AWS wrapper worker count (clamped)
                                                (AWS_WRAPPER_MAX_WORKERS).
            subsystem_ok:                       Per-subsystem active status map
                                                (True=active, False=inactive).
        """
        self.storage_base_path = storage_base_path
        self.pbkdf2_iterations = pbkdf2_iterations
        self.faiss_compaction_vector_threshold = faiss_compaction_vector_threshold
        self.faiss_compaction_delete_ratio = faiss_compaction_delete_ratio
        self.topic_cluster_cache_ttl = topic_cluster_cache_ttl
        self.redis_fallback_ttl_secs = redis_fallback_ttl_secs
        self.personalized_index_weight = personalized_index_weight
        self.global_index_weight = global_index_weight
        self.aws_wrapper_max_workers = aws_wrapper_max_workers
        # Per-subsystem active status map (True=active, False=inactive)
        self.subsystem_ok: Dict[Subsystem, bool] = subsystem_ok

    @classmethod
    def from_env(cls) -> "PersonalizedRAGConfig":
        """Parse settings from environment variables and return a PersonalizedRAGConfig instance.

        On critical parse failure: raises SystemExit(1) — Global Hard Failure.
        """
        # -- 1. Critical settings (Global Hard Failure) -----------------------
        storage_base_path = _parse_str_critical("STORAGE_BASE_PATH")
        pbkdf2_iterations = _parse_int_critical("PBKDF2_ITERATIONS", min_val=600_000)

        # -- 2. Subsystem settings (Subsystem Hard Failure) -------------------
        # subsystem_ok keys always use Subsystem Enum — ensures type safety
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
        # Disable FAISS Compaction subsystem if either setting fails
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

        # Weight sum validation: catches operator misconfiguration early.
        # Normalization is a silent modification that violates Zero Trust — only log WARNING.
        weight_sum = p_weight + g_weight
        if abs(weight_sum - 1.0) > tolerance:
            logger.warning(
                "[CONFIG] PERSONALIZED_INDEX_WEIGHT=%.4f + GLOBAL_INDEX_WEIGHT=%.4f "
                "= %.4f (expected ~1.0, tolerance=+/-%.2f). "
                "Verify weights are configured correctly.",
                p_weight,
                g_weight,
                weight_sum,
                tolerance,
            )

        # Redis fallback TTL is an infra setting — use default without disabling subsystem
        redis_ttl, _ = _parse_int_subsystem(
            "REDIS_FALLBACK_TTL_SECS",
            default=300,
            subsystem=Subsystem.PERSONALIZED_INDEX,
        )

        # -- 3. Range-clamped settings ----------------------------------------
        def _cpu_heuristic() -> int:
            cpu = os.cpu_count() or 1
            return min(32, cpu + 4)

        aws_workers = _parse_int_clamped(
            "AWS_WRAPPER_MAX_WORKERS",
            default_factory=_cpu_heuristic,
            range_=cls._AWS_WORKERS_RANGE,
        )

        # -- 4. Subsystem DISABLED observability logging ----------------------
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


# ---------------------------------------------------------------------------
# Phase 3 streaming configuration validation class
# ---------------------------------------------------------------------------


class RealtimeStreamingConfig:
    """Configuration validation class for v9.0 Phase 3 Realtime Streaming.

    Usage:
        cfg = RealtimeStreamingConfig.from_env()  # call once during bootstrap

    Responsibilities (per 3-0/3-5 SSOT policy):
        - Loads OS environment variables based on the schema and defaults defined
          in StreamingConfig (backend/core/config/streaming.py).
        - Centrally enforces boundary checks (clamping) and validity validation.
        - On parse failure, marks only the REALTIME_STREAMING subsystem as DEGRADED
          while keeping existing non-streaming endpoints alive (Subsystem Hard Failure).

    Validation timing (Fail-Fast):
        Must be performed at application startup (Bootstrap/Startup), not at request time.

    Optional environment variables (parse failure disables only the affected subsystem):
        SSE_KEEPALIVE_INTERVAL_SECS  (int, default: 15, range: 5-60)
        STREAM_BUFFER_MAX_SIZE       (int, default: 100, range: 10-1000)
        STREAM_TIMEOUT_SECS          (int, default: 120, range: 30-600)
        LANGGRAPH_STREAM_VERSION     (str, default: "v2", allowed: "v1"/"v2")

    Security policy:
        Sensitive data (user IDs, tokens, etc.) must never be written to logs.
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
        """Initialize a RealtimeStreamingConfig instance.

        Use the :meth:`from_env` class method instead of calling this directly.
        All arguments are keyword-only.

        Args:
            keepalive_interval_secs: SSE keepalive send interval in seconds
                                     (SSE_KEEPALIVE_INTERVAL_SECS).
            buffer_max_size:         Maximum streaming buffer size
                                     (STREAM_BUFFER_MAX_SIZE).
            timeout_secs:            Maximum streaming session duration in seconds
                                     (STREAM_TIMEOUT_SECS).
            stream_version:          LangGraph streaming protocol version ("v1" or "v2")
                                     (LANGGRAPH_STREAM_VERSION).
            subsystem_ok:            Per-subsystem active status map
                                     (True=active, False=DEGRADED).
        """
        self.keepalive_interval_secs = keepalive_interval_secs
        self.buffer_max_size = buffer_max_size
        self.timeout_secs = timeout_secs
        self.stream_version = stream_version
        # Per-subsystem active status map: managed internally with Enum keys;
        # convert to .value only at the boundary.
        self.subsystem_ok: Dict[Subsystem, bool] = subsystem_ok

    @classmethod
    def from_env(cls) -> "RealtimeStreamingConfig":
        """Parse streaming settings from environment variables and return a RealtimeStreamingConfig instance.

        On parse failure: marks REALTIME_STREAMING subsystem as inactive — Subsystem Hard Failure.
        Does not halt the server; existing non-streaming APIs remain operational.
        """
        # Reference public constant aliases — do not reference underscore-prefixed internal constants directly
        from backend.core.config.streaming import (
            STREAMING_BUFFER_MAX_SIZE_RANGE,
            STREAMING_DEFAULT_BUFFER_MAX_SIZE,
            STREAMING_DEFAULT_KEEPALIVE_INTERVAL_SECS,
            STREAMING_DEFAULT_STREAM_VERSION,
            STREAMING_DEFAULT_TIMEOUT_SECS,
            STREAMING_ENV_BUFFER_MAX_SIZE,
            STREAMING_ENV_KEEPALIVE_INTERVAL,
            STREAMING_ENV_STREAM_VERSION,
            STREAMING_ENV_TIMEOUT,
            STREAMING_KEEPALIVE_INTERVAL_RANGE,
            STREAMING_TIMEOUT_RANGE,
            STREAMING_VALID_STREAM_VERSIONS,
        )

        # Dict[Subsystem, bool]: Enum keys ensure internal type safety
        subsystem_ok: Dict[Subsystem, bool] = {}

        # -- Subsystem settings (Subsystem Hard Failure) ----------------------
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

        # String enum validation (invalid version falls back to default)
        # Check ENV key existence first to avoid unnecessary .strip() on default value
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

        # Disable REALTIME_STREAMING subsystem if any setting fails
        subsystem_ok[Subsystem.REALTIME_STREAMING] = (
            ok_ka and ok_buf and ok_to and ok_ver
        )

        # -- Subsystem DEGRADED observability logging -------------------------
        _log_subsystem_state(subsystem_ok, state_label=SubsystemHealthState.DEGRADED)

        return cls(
            keepalive_interval_secs=keepalive,
            buffer_max_size=buffer_size,
            timeout_secs=timeout,
            stream_version=stream_version,
            subsystem_ok=subsystem_ok,
        )


# ---------------------------------------------------------------------------
# Phase 4 knowledge graph configuration validation class
# ---------------------------------------------------------------------------


class GraphEngineConfig:
    """Configuration validation class for v9.0 Phase 4 Knowledge Graph.

    Usage:
        cfg = GraphEngineConfig.from_env()  # call once during bootstrap

    Responsibilities (per 4-5 SSOT policy):
        - Loads OS environment variables by referencing constants (ENV keys, defaults,
          ranges) defined in the backend.core.config.graph module. (No hardcoding.)
        - On integer range violation: clamps to boundary + emits a structured WARNING log.
        - On GRAPH_DB_URL unset or empty: falls back to networkx in-memory (INFO log, not an error).
        - On integer parse failure (non-integer value): marks only the GRAPH_ENGINE subsystem
          as DEGRADED (Subsystem Fail-fast). Overall server startup is not interrupted.

    Environment variables under validation (all referenced via GraphConfig SSOT constants):
        GRAPH_MAX_TRAVERSAL_DEPTH             (int, default: 3,     range: 1-5)
        NEXT_PUBLIC_MAX_GRAPH_NODES           (int, default: 500,   range: 50-2000)
        GRAPH_DB_URL                          (str, default: "",    empty falls back to networkx)
        GRAPH_MIGRATION_NODE_THRESHOLD        (int, default: 10000, range: 5000-50000)
        GRAPH_MIGRATION_CONCURRENCY_THRESHOLD (int, default: 10,    range: 5-100)

    Security policy:
        The DB connection string (GRAPH_DB_URL) value must never be written to logs.
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
        """Initialize a GraphEngineConfig instance.

        Use the :meth:`from_env` class method instead of calling this directly.
        All arguments are keyword-only.

        Args:
            max_traversal_depth:             Maximum graph traversal depth
                                             (GRAPH_MAX_TRAVERSAL_DEPTH).
            max_graph_nodes:                 Maximum node count for frontend rendering
                                             (NEXT_PUBLIC_MAX_GRAPH_NODES).
            db_url:                          External graph DB connection URL.
                                             Empty string means networkx in-memory fallback.
                                             (GRAPH_DB_URL) Security: never log this value.
            migration_node_threshold:        Node count threshold that triggers migration
                                             (GRAPH_MIGRATION_NODE_THRESHOLD).
            migration_concurrency_threshold: Max concurrent migration operations
                                             (GRAPH_MIGRATION_CONCURRENCY_THRESHOLD).
            subsystem_ok:                    Per-subsystem active status map
                                             (True=active, False=DEGRADED).
        """
        self.max_traversal_depth = max_traversal_depth
        self.max_graph_nodes = max_graph_nodes
        # Security: DB URL is kept only as an instance variable; never log it
        self.db_url = db_url
        self.migration_node_threshold = migration_node_threshold
        self.migration_concurrency_threshold = migration_concurrency_threshold
        # Per-subsystem active status map (True=active, False=DEGRADED)
        self.subsystem_ok: Dict[Subsystem, bool] = subsystem_ok

    @classmethod
    def from_env(cls) -> "GraphEngineConfig":
        """Parse graph settings from environment variables and return a GraphEngineConfig instance.

        - Integer parse failure (non-integer value): GRAPH_ENGINE subsystem DEGRADED — Subsystem Hard Failure.
        - Integer out of range: clamped + WARNING log — Graceful Fallback.
        - GRAPH_DB_URL unset or empty: networkx in-memory fallback — INFO log (not an error).
        - Server startup is never interrupted under any condition.
        """
        # SSOT: import all constants from graph.py — no hardcoding
        from backend.core.config.graph import (
            DEFAULT_DB_URL,
            DEFAULT_MAX_GRAPH_NODES,
            DEFAULT_MAX_TRAVERSAL_DEPTH,
            DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD,
            DEFAULT_MIGRATION_NODE_THRESHOLD,
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

        # subsystem_ok keys always use Subsystem Enum — ensures type safety
        subsystem_ok: Dict[Subsystem, bool] = {}

        # -- Integer settings: Clamp + WARNING (out of range) / DEGRADED (parse failure) --
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

        # -- GRAPH_DB_URL: empty value = networkx fallback (not an error) -----
        # Security policy: DB URL value itself must never be written to logs
        raw_db_url = os.environ.get(ENV_DB_URL, DEFAULT_DB_URL).strip()
        if not raw_db_url:
            logger.info(
                "[CONFIG][GRAPH] '%s' is not set or empty; "
                "using networkx in-memory fallback (no external graph DB).",
                ENV_DB_URL,
            )
        db_url = raw_db_url

        # -- Subsystem health decision: DEGRADED if any parse failure ---------
        # GRAPH_DB_URL parse failure is NOT a subsystem deactivation condition
        # (empty value is a valid state)
        subsystem_ok[Subsystem.GRAPH_ENGINE] = ok_depth and ok_nodes and ok_mn and ok_mc

        # -- Subsystem DEGRADED observability logging -------------------------
        _log_subsystem_state(subsystem_ok, state_label=SubsystemHealthState.DEGRADED)

        return cls(
            max_traversal_depth=max_depth,
            max_graph_nodes=max_nodes,
            db_url=db_url,
            migration_node_threshold=migration_node,
            migration_concurrency_threshold=migration_concurrency,
            subsystem_ok=subsystem_ok,
        )

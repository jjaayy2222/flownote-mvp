# backend/core/health_registry.py

"""
HealthRegistry - Single Source of Truth (SSOT) based subsystem status registry
==============================================================================

Architectural Principles:
  - Single Pod: In-process module-scoped singleton as primary reference
  - Multi-Pod: Redis as SSOT to resolve deployment state inconsistencies across pods
  - CAP Trade-off: Graceful fallback to local cache within REDIS_FALLBACK_TTL_SECS
    during Redis partition; hard fallback after TTL expires
  - Intra-process Lock: threading.Lock only guarantees single-session initialization
    within the same process. Inter-process coordination requires separate mechanisms
    (e.g., file locks).

SSOT Communication Sequence:
  1. Publish: Edge Worker -> registry.report(subsystem, status)
  2. Retrieve: /health controller -> registry.get_summary() (no polling)
  3. Alert: Transition to DEGRADED exposes HTTP 503 response and Prometheus metrics

Security Principles:
  - Sensitive information (connection strings, keys) is never logged
  - User identifiable information must not be included in Redis keys
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Subsystem Status Enum
# -----------------------------------------------------------------------------


class SubsystemStatus(str, Enum):
    """Subsystem operational status."""

    HEALTHY = "healthy"  # Operating normally
    DEGRADED = (
        "degraded"  # Disabled due to configuration error etc. (Service maintained)
    )
    FAILED = "failed"  # Runtime failure detected (Recovery attempt possible)


# -----------------------------------------------------------------------------
# Module Scope Singleton Lock - For Double-checked locking pattern
# This Lock only guarantees single session initialization between threads
# in the same process (Intra-process).
# Inter-process synchronization requires introducing an OS-level file lock
# (single server standard) or Redis distributed lock (multi-server/container).
# -----------------------------------------------------------------------------
_REGISTRY_LOCK = threading.Lock()
_registry_instance: Optional["HealthRegistry"] = None


# -----------------------------------------------------------------------------
# HealthRegistry
# -----------------------------------------------------------------------------


class HealthRegistry:
    """
    Subsystem status registry singleton.

    Usage:
        registry = HealthRegistry.get_instance(
            redis_fallback_ttl_secs=300,
            redis_url="redis://localhost:6379",   # Optional: Multi-pod environment
        )
        registry.report("faiss_compaction", SubsystemStatus.DEGRADED)
        summary = registry.get_summary()
        ttl_remaining = registry.get_fallback_ttl_remaining_seconds()
    """

    # Store Redis state in a single Hash to retrieve all at once with HGETALL
    _REDIS_HASH_KEY = "flownote:health:summary"  # Immutable summary hash key
    # TTL: Applied to the entire Hash (no individual field expiration)

    def __init__(
        self,
        redis_fallback_ttl_secs: int = 300,
        redis_url: Optional[str] = None,
    ) -> None:
        """
        Args:
            redis_fallback_ttl_secs: Max time (seconds) to allow local cache during Redis partition.
            redis_url: Redis connection URL (In-process mode if not specified).
                       For security, this value is never logged.
        """
        self._redis_fallback_ttl_secs = redis_fallback_ttl_secs
        self._redis_url = redis_url

        # In-process state storage
        self._local_state: Dict[str, SubsystemStatus] = {}
        self._state_lock = threading.Lock()

        # Redis fallback tracking
        self._redis_available: bool = True
        self._redis_unavailable_since: Optional[float] = None  # monotonic timestamp
        self._logged_empty_hash_fallback: bool = False  # Anti-log-spam guard

        # Redis client (Lazy initialization, fork-safe)
        self._redis_client = None
        self._redis_init_lock = threading.Lock()

    # -- Singleton Factory -----------------------------------------------------

    @classmethod
    def get_instance(
        cls,
        redis_fallback_ttl_secs: int = 300,
        redis_url: Optional[str] = None,
    ) -> "HealthRegistry":
        """
        Returns a single instance within the process using Double-checked locking.

        Concurrency Guarantee:
          - Prevents race conditions between intra-process threads via module-scope _REGISTRY_LOCK.
          - Each worker process has an independent instance after fork (single session per process).
        """
        global _registry_instance
        if _registry_instance is None:
            with _REGISTRY_LOCK:
                # Double-checked locking
                if _registry_instance is None:
                    logger.info(
                        "[HEALTH_REGISTRY] Initializing singleton instance "
                        "(redis=%s).",
                        "enabled" if redis_url else "disabled (single-pod mode)",
                    )
                    _registry_instance = cls(
                        redis_fallback_ttl_secs=redis_fallback_ttl_secs,
                        redis_url=redis_url,
                    )
        else:
            # If an already created singleton is allowed with different settings, log a warning.
            # The Redis URL value itself is never logged due to potential credentials.
            try:
                inst = _registry_instance
                configured_ttl = getattr(inst, "_redis_fallback_ttl_secs", None)
                configured_redis = getattr(inst, "_redis_url", None)
                ttl_mismatch = redis_fallback_ttl_secs != configured_ttl
                redis_mismatch = redis_url is not None and redis_url != configured_redis
                if ttl_mismatch or redis_mismatch:
                    logger.warning(
                        "[HEALTH_REGISTRY] get_instance called with config that "
                        "differs from existing singleton "
                        "(redis_enabled_current=%s, redis_fallback_ttl_current=%r; "
                        "redis_enabled_requested=%s, redis_fallback_ttl_requested=%r). "
                        "Existing singleton configuration will be used.",
                        configured_redis is not None,
                        configured_ttl,
                        redis_url is not None,
                        redis_fallback_ttl_secs,
                    )
            except Exception:
                logger.exception(
                    "[HEALTH_REGISTRY] Failed to compare singleton configuration "
                    "in get_instance."
                )
        return _registry_instance

    # -- Redis Client Lazy Initialization (Fork-safe) --------------------------

    def _get_redis(self):
        """
        Lazily initializes and returns the Redis client (Fork-safe Lazy Initialization).
        Creates connection only after process fork to prevent socket sharing crashes.
        Returns None on connection failure and switches to In-process fallback mode.
        """
        if self._redis_url is None:
            return None

        if self._redis_client is not None:
            return self._redis_client

        with self._redis_init_lock:
            if self._redis_client is not None:
                return self._redis_client
            try:
                import redis  # type: ignore

                client = redis.from_url(
                    self._redis_url,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    decode_responses=True,
                )
                client.ping()
                self._redis_client = client
                logger.info("[HEALTH_REGISTRY] Redis connection established.")
            except Exception:
                # Redis URL is not logged for security reasons
                logger.warning(
                    "[HEALTH_REGISTRY] Redis connection failed. "
                    "Falling back to in-process state (single-pod mode)."
                )
                self._redis_client = None

        return self._redis_client

    # -- Status Reporting (Publish) --------------------------------------------

    def report(self, subsystem: str, status: SubsystemStatus) -> None:
        """
        Records the subsystem status in the registry.

        [Edge Worker Thread] -> report() called -> Registry status updated.

        Args:
            subsystem: Subsystem identifier (e.g., "faiss_compaction")
            status: SubsystemStatus enum value
        """
        with self._state_lock:
            prev = self._local_state.get(subsystem)
            self._local_state[subsystem] = status

        if prev != status:
            logger.info(
                "[HEALTH_REGISTRY] '%s': %s → %s",
                subsystem,
                prev.value if prev else "unknown",
                status.value,
            )

        # Try Redis SSOT synchronization (Multi-pod mode)
        self._publish_to_redis(subsystem, status)

    def _publish_to_redis(self, subsystem: str, status: SubsystemStatus) -> None:
        """
        Publishes the subsystem status to Redis Hash using HSET.

        Stores all subsystem statuses as fields in a single Hash (_REDIS_HASH_KEY),
        allowing full retrieval with one HGETALL instead of N GETs.
        Starts TTL timer on failure.
        """
        client = self._get_redis()
        if client is None:
            return

        try:
            client.hset(self._REDIS_HASH_KEY, subsystem, status.value)
            # Apply TTL to entire Hash (auto-expires if no subsystem reports)
            client.expire(self._REDIS_HASH_KEY, self._redis_fallback_ttl_secs * 2)
            if not self._redis_available:
                logger.info(
                    "[HEALTH_REGISTRY] Redis connection restored. "
                    "Resuming SSOT synchronization."
                )
            self._redis_available = True
            self._redis_unavailable_since = None
        except Exception:
            self._on_redis_failure()

    # -- Status Retrieval (Retrieve) -------------------------------------------

    def get_summary(self) -> Dict[str, str]:
        """
        Returns the current status of all subsystems.
        The /health controller calls this only upon Ping reception, without polling.

        If Redis is available: References Redis SSOT.
        If Redis is partitioned: Within REDIS_FALLBACK_TTL_SECS -> Returns local cache (Stale State allowed).
                                 TTL exceeded -> Local cache invalidated, Hard Fallback (FAILED).

        Returns:
            {"subsystem_name": "healthy"|"degraded"|"failed", ...}
        """
        # Attempt to retrieve Redis SSOT
        redis_state = self._fetch_from_redis()
        if redis_state is not None:
            # If Redis is normal but no reports exist yet (returns empty hash {}),
            # expose subsystem states accumulated in the worker local cache
            # to prevent state concealment.
            if not redis_state:
                should_log = False
                with self._state_lock:
                    local_cache = {k: v.value for k, v in self._local_state.items()}
                    if local_cache and not self._logged_empty_hash_fallback:
                        should_log = True
                        self._logged_empty_hash_fallback = True

                if local_cache:
                    if should_log:
                        logger.info(
                            "[HEALTH_REGISTRY] Redis returned empty hash. "
                            "Falling back to local cache to expose existing subsystem states "
                            "(startup/lag condition)."
                        )
                    return local_cache
            # Reset guard upon successful data reception
            else:
                with self._state_lock:
                    if self._logged_empty_hash_fallback:
                        self._logged_empty_hash_fallback = False
            return redis_state

        # Redis Partition - Check fallback TTL
        if self._redis_unavailable_since is not None:
            elapsed = time.monotonic() - self._redis_unavailable_since
            if elapsed > self._redis_fallback_ttl_secs:
                logger.error(
                    "[HEALTH_REGISTRY] Redis fallback TTL (%ds) exceeded (elapsed=%.1fs). "
                    "Invalidating local cache. Hard fallback activated.",
                    self._redis_fallback_ttl_secs,
                    elapsed,
                )
                # Invalidate local cache: treat all subsystems as FAILED
                with self._state_lock:
                    return {k: SubsystemStatus.FAILED.value for k in self._local_state}

        # Return local cache normally within TTL (Graceful Fallback)
        with self._state_lock:
            return {k: v.value for k, v in self._local_state.items()}

    def _fetch_from_redis(self) -> Optional[Dict[str, str]]:
        """
        Retrieves entire status from Redis Hash with a single Round-trip using HGETALL.

        Prevents blocking O(N) execution of KEYS * by using HGETALL.
        Returns None on failure (switches to In-process fallback).
        An empty dict {} means "Redis normal, no subsystems reported yet",
        so it is not treated the same as None. Returning None for an empty hash
        causes a bug that misjudges a normal Redis as partitioned.
        """
        client = self._get_redis()
        if client is None:
            return None

        try:
            result: Dict[str, str] = client.hgetall(self._REDIS_HASH_KEY)
            self._redis_available = True
            self._redis_unavailable_since = None
            # Empty dict {} is also a valid result - do not convert to None
            return result
        except Exception:
            self._on_redis_failure()
            return None

    def _on_redis_failure(self) -> None:
        """Starts the fallback timer when a Redis failure occurs."""
        if self._redis_available:
            self._redis_available = False
            self._redis_unavailable_since = time.monotonic()
            logger.warning(
                "[HEALTH_REGISTRY] Redis became unavailable. "
                "Graceful fallback activated (TTL=%ds). "
                "Monitor 'redis_fallback_ttl_remaining_seconds' metric.",
                self._redis_fallback_ttl_secs,
            )

    # -- Prometheus Metrics ----------------------------------------------------

    def get_fallback_ttl_remaining_seconds(self) -> float:
        """
        Returns the remaining Redis fallback TTL in seconds.

        Metric name: redis_fallback_ttl_remaining_seconds
        Calculation: Exact timestamp difference (not an estimate)
        Exposed to: Prometheus scraping endpoint (/metrics)

        Returns:
            Remaining TTL in seconds. Full TTL if Redis is healthy.
            0.0 or less if TTL is exceeded.
        """
        if self._redis_unavailable_since is None:
            return float(self._redis_fallback_ttl_secs)

        elapsed = time.monotonic() - self._redis_unavailable_since
        remaining = self._redis_fallback_ttl_secs - elapsed
        return max(0.0, remaining)

    # -- Individual/Overall Status Checking (For SSOT Integration) -------------

    def is_ok(
        self,
        subsystem: str | Enum,
        precomputed_summary: Optional[Dict[str, str]] = None,
        *,
        strict: bool = False,
    ) -> bool:
        """
        Checks if a specific subsystem is in a normal (HEALTHY) state via the Single Source of Truth (SSOT).

        - Used for fail-fast connection checks at the router/application layer.
        - Returns False if explicitly in DEGRADED or FAILED state.

        Args:
            subsystem: Subsystem identifier to check (string or Enum)
            precomputed_summary: (Optional) Pre-queried status summary dict for optimization.
                                 Used to minimize Redis I/O during repeated calls.
            strict: (Optional) If True, an unreported (None) subsystem is considered abnormal (False).
                    Useful for preventing wiring mistakes from typos or missing configs. (Default: False)
        """
        if isinstance(subsystem, Enum):
            # Explicit string conversion in case Enum value is not a string (e.g. integer Enum)
            key = str(subsystem.value)
        elif isinstance(subsystem, str):
            key = subsystem
        else:
            raise TypeError(
                f"[HEALTH_REGISTRY] Unsupported subsystem type: {type(subsystem).__name__}. "
                "subsystem must be a string or Enum."
            )

        summary = (
            precomputed_summary
            if precomputed_summary is not None
            else self.get_summary()
        )
        status = summary.get(key)

        # sourcery skip: assign-if-exp
        if status is None:
            return not strict

        return status == SubsystemStatus.HEALTHY.value

    def is_healthy(self) -> bool:
        """
        Returns whether the overall system status is HEALTHY.
        False if any subsystem is FAILED/DEGRADED.
        Used by the /health controller to branch between HTTP 200 and 503.
        """
        summary = self.get_summary()
        return all(v == SubsystemStatus.HEALTHY.value for v in summary.values())

    def get_http_status_code(self) -> int:
        """
        Returns the /health response code.
          - 200: All subsystems HEALTHY
          - 503: One or more DEGRADED/FAILED (AWS ALB/K8s traffic block signal)
        """
        return 200 if self.is_healthy() else 503

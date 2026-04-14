# backend/core/health_registry.py

"""
HealthRegistry — 단일 진실 공급원(SSOT) 기반 서브시스템 상태 레지스트리
==========================================================================

아키텍처 원칙:
  - 단일 파드: 모듈 스코프 싱글톤(In-process) 우선 참조
  - 멀티 파드: Redis를 SSOT로 사용, 파드 간 배포 상태 불일치 해소
  - CAP 트레이드오프: Redis 파티션 시 REDIS_FALLBACK_TTL_SECS 내에서
    로컬 캐시로 Graceful Fallback, TTL 초과 시 Hard Fallback
  - Intra-process Lock: threading.Lock은 동일 프로세스 내 단일 세션
    초기화만 보장. Inter-process 조율은 별도 메커니즘(파일 락 등) 필요.

SSOT 통신 시퀀스:
  1. Publish: 에지 워커 → registry.report(subsystem, status)
  2. Retrieve: /health 컨트롤러 → registry.get_summary() (폴링 없음)
  3. Alert: DEGRADED 전환 시 HTTP 503 응답 + Prometheus 메트릭 노출

보안 원칙:
  - 민감 정보(연결 문자열, 키)는 절대 로그에 기록하지 않음
  - Redis 키에 사용자 식별 정보 포함 금지
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 서브시스템 상태 열거형
# ─────────────────────────────────────────────────────────────────────────────


class SubsystemStatus(str, Enum):
    """서브시스템 운영 상태."""

    HEALTHY = "healthy"      # 정상 운영 중
    DEGRADED = "degraded"    # 설정 오류 등으로 비활성화 (서비스는 유지)
    FAILED = "failed"        # 런타임 장애 감지 (복구 시도 가능)


# ─────────────────────────────────────────────────────────────────────────────
# 모듈 스코프 싱글톤 락 — Double-checked locking 패턴용
# 이 Lock은 동일 프로세스 내(Intra-process) 스레드 간 단일 세션 초기화만 보장.
# 프로세스 간(Inter-process) 동기화는 OS 레벨 파일 락(단일 서버 표준) 또는
# Redis 분산 락(다중 서버/컨테이너 환경)을 별도로 도입해야 함.
# ─────────────────────────────────────────────────────────────────────────────
_REGISTRY_LOCK = threading.Lock()
_registry_instance: Optional["HealthRegistry"] = None


# ─────────────────────────────────────────────────────────────────────────────
# HealthRegistry
# ─────────────────────────────────────────────────────────────────────────────


class HealthRegistry:
    """
    서브시스템 상태 레지스트리 싱글톤.

    사용법:
        registry = HealthRegistry.get_instance(
            redis_fallback_ttl_secs=300,
            redis_url="redis://localhost:6379",   # 선택: 멀티 파드 환경
        )
        registry.report("faiss_compaction", SubsystemStatus.DEGRADED)
        summary = registry.get_summary()
        ttl_remaining = registry.get_fallback_ttl_remaining_seconds()
    """

    # Redis 상태를 단일 Hash에 저장하여 HGETALL 한 번으로 전체 조회 (KEYS 살포 O(N) 블로킹 제거)
    _REDIS_HASH_KEY = "flownote:health:summary"  # 불변 summary hash key
    # TTL: Hash 전체에 적용 (개별 필드 만료 없음)

    def __init__(
        self,
        redis_fallback_ttl_secs: int = 300,
        redis_url: Optional[str] = None,
    ) -> None:
        """
        Args:
            redis_fallback_ttl_secs: Redis 파티션 시 로컬 캐시 허용 최대 시간(초).
            redis_url: Redis 연결 URL (미지정 시 단일 파드 In-process 모드).
                       보안상 이 값은 절대 로그에 기록하지 않음.
        """
        self._redis_fallback_ttl_secs = redis_fallback_ttl_secs
        self._redis_url = redis_url

        # In-process 상태 저장소
        self._local_state: Dict[str, SubsystemStatus] = {}
        self._state_lock = threading.Lock()

        # Redis 폴백 추적
        self._redis_available: bool = True
        self._redis_unavailable_since: Optional[float] = None  # monotonic timestamp

        # Redis 클라이언트 (지연 초기화, fork-safe)
        self._redis_client = None
        self._redis_init_lock = threading.Lock()

    # ── 싱글톤 팩토리 ─────────────────────────────────────────────────────

    @classmethod
    def get_instance(
        cls,
        redis_fallback_ttl_secs: int = 300,
        redis_url: Optional[str] = None,
    ) -> "HealthRegistry":
        """
        Double-checked locking 패턴으로 프로세스 내 단일 인스턴스를 반환한다.

        동시성 보장:
          - 모듈 스코프 _REGISTRY_LOCK을 통해 Intra-process 스레드 간 race condition 방지.
          - 각 워커 프로세스는 포크 이후 독립적인 인스턴스를 가짐 (프로세스별 단일 세션).
        """
        global _registry_instance
        if _registry_instance is None:
            with _REGISTRY_LOCK:
                # 락 획득 후 이중 확인 (Double-checked locking)
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
            # 이미 생성된 싱글턴이 있을 때 다른 설정으로 호용되면 경고를 남김.
            # Redis URL 값 자체는 credential 포함 가능성이 있으므로 절대 로그에 기록하지 않음.
            try:
                inst = _registry_instance
                configured_ttl = getattr(inst, "_redis_fallback_ttl_secs", None)
                configured_redis = getattr(inst, "_redis_url", None)
                ttl_mismatch = (
                    redis_fallback_ttl_secs != configured_ttl
                )
                redis_mismatch = (
                    redis_url is not None
                    and redis_url != configured_redis
                )
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

    # ── Redis 클라이언트 지연 초기화 (Fork-safe) ─────────────────────────

    def _get_redis(self):
        """
        Redis 클라이언트를 지연 초기화하여 반환한다 (Fork-safe Lazy Initialization).
        프로세스 포크 이후에만 연결을 생성하여 소켓 공유 크래시를 방지.
        연결 실패 시 None을 반환하며 In-process 폴백 모드로 전환.
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
                # Redis URL은 보안상 로그에 기록하지 않음
                logger.warning(
                    "[HEALTH_REGISTRY] Redis connection failed. "
                    "Falling back to in-process state (single-pod mode)."
                )
                self._redis_client = None

        return self._redis_client

    # ── 상태 보고 (Publish) ───────────────────────────────────────────────

    def report(self, subsystem: str, status: SubsystemStatus) -> None:
        """
        서브시스템 상태를 레지스트리에 기록한다.

        [에지 워커 스레드] → report() 호출 → 레지스트리 상태 갱신.

        Args:
            subsystem: 서브시스템 식별자 (예: "faiss_compaction")
            status: SubsystemStatus 열거값
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

        # Redis SSOT 동기화 시도 (멀티 파드 모드)
        self._publish_to_redis(subsystem, status)

    def _publish_to_redis(self, subsystem: str, status: SubsystemStatus) -> None:
        """
        Redis Hash에 서브시스템 상태를 HSET으로 게시한다.

        단일 Hash(_REDIS_HASH_KEY)에 모든 서브시스템 상태를 field로 저장하며,
        GET N회 대신 HGETALL 1회로 전체 조회 가능 (라운드트립 1회로 축소).
        실패 시 TTL 타이머 시작.
        """
        client = self._get_redis()
        if client is None:
            return

        try:
            client.hset(self._REDIS_HASH_KEY, subsystem, status.value)
            # Hash 전체에 TTL 적용 (서브시스템 보고 없으면 자동 만료)
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

    # ── 상태 조회 (Retrieve) ──────────────────────────────────────────────

    def get_summary(self) -> Dict[str, str]:
        """
        모든 서브시스템의 현재 상태를 반환한다.
        /health 컨트롤러는 주기적 폴링 없이 핑(Ping) 수신 시에만 이 메서드를 호출한다.

        Redis 가용 시: Redis SSOT 참조.
        Redis 파티션 시: REDIS_FALLBACK_TTL_SECS 내 → 로컬 캐시 반환 (Stale State 허용).
                         TTL 초과 → 로컬 캐시 무효화 후 Hard Fallback (FAILED 처리).

        Returns:
            {"subsystem_name": "healthy"|"degraded"|"failed", ...}
        """
        # Redis SSOT 조회 시도
        redis_state = self._fetch_from_redis()
        if redis_state is not None:
            return redis_state

        # Redis 파티션 — 폴백 TTL 확인
        if self._redis_unavailable_since is not None:
            elapsed = time.monotonic() - self._redis_unavailable_since
            if elapsed > self._redis_fallback_ttl_secs:
                logger.error(
                    "[HEALTH_REGISTRY] Redis fallback TTL (%ds) exceeded (elapsed=%.1fs). "
                    "Invalidating local cache. Hard fallback activated.",
                    self._redis_fallback_ttl_secs,
                    elapsed,
                )
                # 로컬 캐시를 무효화: 모든 서브시스템을 FAILED로 처리
                with self._state_lock:
                    return {k: SubsystemStatus.FAILED.value for k in self._local_state}

        # TTL 내 로컬 캐시 정상 반환 (Graceful Fallback)
        with self._state_lock:
            return {k: v.value for k, v in self._local_state.items()}

    def _fetch_from_redis(self) -> Optional[Dict[str, str]]:
        """
        Redis Hash에서 HGETALL로 전체 상태를 단일 Round-trip으로 조회한다.

        KEYS *를 O(N) 블로킹 명령 실행 없이 HGETALL로 맨점 방지.
        실패 시 None 반환 (In-process 폴백 전환).
        """
        client = self._get_redis()
        if client is None:
            return None

        try:
            result: Dict[str, str] = client.hgetall(self._REDIS_HASH_KEY)
            self._redis_available = True
            self._redis_unavailable_since = None
            # Hash가 비어있으면 로컈 상태 참조
            return result if result else None
        except Exception:
            self._on_redis_failure()
            return None

    def _on_redis_failure(self) -> None:
        """Redis 장애 발생 시 폴백 타이머를 시작한다."""
        if self._redis_available:
            self._redis_available = False
            self._redis_unavailable_since = time.monotonic()
            logger.warning(
                "[HEALTH_REGISTRY] Redis became unavailable. "
                "Graceful fallback activated (TTL=%ds). "
                "Monitor 'redis_fallback_ttl_remaining_seconds' metric.",
                self._redis_fallback_ttl_secs,
            )

    # ── Prometheus 메트릭 ─────────────────────────────────────────────────

    def get_fallback_ttl_remaining_seconds(self) -> float:
        """
        Redis 폴백 잔여 TTL을 초 단위(Seconds)로 반환한다.

        메트릭명: redis_fallback_ttl_remaining_seconds
        계산 방식: 엄밀한 Timestamp 차이 연산 (추정값 아님)
        노출 대상: Prometheus 스크래핑 엔드포인트 (/metrics)

        Returns:
            잔여 TTL(초). Redis 정상 시 full TTL 값 반환.
            0.0 이하 시 TTL 초과 상태.
        """
        if self._redis_unavailable_since is None:
            return float(self._redis_fallback_ttl_secs)

        elapsed = time.monotonic() - self._redis_unavailable_since
        remaining = self._redis_fallback_ttl_secs - elapsed
        return max(0.0, remaining)

    # ── 전체 상태 판정 (/health 응답용) ──────────────────────────────────

    def is_healthy(self) -> bool:
        """
        시스템 전체 상태가 HEALTHY인지 반환한다.
        하나라도 FAILED/DEGRADED 서브시스템이 있으면 False.
        /health 컨트롤러에서 HTTP 200 vs 503 분기에 사용.
        """
        summary = self.get_summary()
        return all(
            v == SubsystemStatus.HEALTHY.value for v in summary.values()
        )

    def get_http_status_code(self) -> int:
        """
        /health 응답 코드를 반환한다.
          - 200: 모든 서브시스템 HEALTHY
          - 503: 하나 이상 DEGRADED/FAILED (AWS ALB/K8s 트래픽 차단 신호)
        """
        return 200 if self.is_healthy() else 503

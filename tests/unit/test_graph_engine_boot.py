# tests/unit/test_graph_engine_boot.py

"""
Phase 4-5 부팅 통합 테스트 (Fail-fast & DEGRADED 폴백 검증)
================================================================

이 모듈은 GraphEngineConfig.from_env()와 HealthRegistry.is_ok() 인터페이스가
연결되기 전(pre-wiring) 단계에서 각 컴포넌트의 계약(Contract)을 독립적으로
검증한다.

검증 목표:
  1. 비정수 파싱 실패 시 서버 전체가 죽지 않고 GRAPH_ENGINE 서브시스템만
     DEGRADED로 격하되는지 확인 (SystemExit 발생 없음).
  2. 범위 초과·미만 값은 Clamping되고 WARNING 로그가 출력되는지 확인.
     → 4개 정수 환경 변수 × 2방향(상한초과/하한미만) = 8케이스 전수 검증.
  3. GRAPH_DB_URL이 없거나 비어있어도 INFO 로그만 남기고 서버가 정상 기동되는지
     확인.
  4. HealthRegistry.is_ok()가 subsystem_ok 상태를 올바르게 반영하는지 확인.

테스트 격리 원칙:
  - 환경 변수: monkeypatch로 테스트마다 주입/제거 (autouse fixture).
  - HealthRegistry 싱글톤: 각 테스트 전 _local_state를 초기화하여 순서 의존성 제거.
  - Logger 이름: 모듈 import를 통해 동적 참조 (하드코딩 금지).

보안 원칙:
  - DB URL 값 자체를 로그에서 검증하거나 실제 크리덴셜을 하드코딩하지 않는다.
  - 개인 식별 정보가 포함된 URL을 사용하지 않는다.
"""

from __future__ import annotations

import logging

import pytest

# ─── SSOT 상수 import (하드코딩 절대 금지) ────────────────────────────────────
import backend.core.config_validator as _cv_module
import backend.core.health_registry as _hr_module
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
from backend.core.config_validator import GraphEngineConfig, Subsystem
from backend.core.health_registry import HealthRegistry, SubsystemStatus

# Logger 이름을 모듈 import에서 동적으로 참조 — 모듈명 변경 시 자동 추적 (하드코딩 금지)
_CONFIG_VALIDATOR_LOGGER: str = _cv_module.logger.name
_HEALTH_REGISTRY_LOGGER: str = _hr_module.logger.name


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

_GRAPH_ENV_KEYS = (
    ENV_MAX_TRAVERSAL_DEPTH,
    ENV_MAX_GRAPH_NODES,
    ENV_DB_URL,
    ENV_MIGRATION_NODE_THRESHOLD,
    ENV_MIGRATION_CONCURRENCY_THRESHOLD,
)


@pytest.fixture(autouse=True)
def clean_graph_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """각 테스트 전에 그래프 관련 환경 변수를 제거하여 격리된 환경을 보장한다."""
    for key in _GRAPH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def isolated_registry(monkeypatch: pytest.MonkeyPatch) -> HealthRegistry:
    """
    테스트 격리용 HealthRegistry 픽스처.

    싱글톤 인스턴스의 _local_state를 초기화하여 테스트 순서에 따른 상태 오염을 방지한다.
    실제 프로덕션 코드(health_registry.py)는 수정하지 않으며,
    monkeypatch를 사용해 _hr_module의 전역 _registry_instance를 테스트 전용
    새 인스턴스로 교체한다.

    테스트 종료 후 monkeypatch가 자동으로 원래 싱글톤 상태를 복원한다.
    """
    fresh = HealthRegistry()  # Redis 없이 In-process 전용 인스턴스 생성
    monkeypatch.setattr(_hr_module, "_registry_instance", fresh)
    return fresh


# ─────────────────────────────────────────────────────────────────────────────
# 1. 정상 기동 — 기본값 사용 (모든 환경 변수 미설정)
# ─────────────────────────────────────────────────────────────────────────────


class TestGraphEngineConfigBootDefault:
    """환경 변수 전체 미설정 시 기본값 기동 검증."""

    def test_boots_successfully_with_defaults(self) -> None:
        """환경 변수 없이 기본값으로 정상 부팅되어야 한다."""
        cfg = GraphEngineConfig.from_env()

        assert cfg.max_traversal_depth == DEFAULT_MAX_TRAVERSAL_DEPTH
        assert cfg.max_graph_nodes == DEFAULT_MAX_GRAPH_NODES
        assert cfg.db_url == DEFAULT_DB_URL
        assert cfg.migration_node_threshold == DEFAULT_MIGRATION_NODE_THRESHOLD
        assert cfg.migration_concurrency_threshold == DEFAULT_MIGRATION_CONCURRENCY_THRESHOLD

    def test_graph_engine_subsystem_is_ok_with_defaults(self) -> None:
        """기본값 기동 시 GRAPH_ENGINE 서브시스템은 정상(ok=True) 상태여야 한다."""
        cfg = GraphEngineConfig.from_env()

        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True

    def test_empty_db_url_does_not_degrade_subsystem(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """GRAPH_DB_URL 미설정은 INFO 로그만 남기고 서브시스템을 DEGRADED하지 않는다."""
        with caplog.at_level(logging.INFO, logger=_CONFIG_VALIDATOR_LOGGER):
            cfg = GraphEngineConfig.from_env()

        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True
        # INFO 로그에 ENV key 이름이 포함되어야 함 (URL 값 자체는 절대 금지)
        assert any(ENV_DB_URL in record.message for record in caplog.records), (
            f"GRAPH_DB_URL 미설정 시 '{ENV_DB_URL}'가 포함된 INFO 로그가 없습니다."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Fail-fast 검증 — 비정수 환경 변수 시 SystemExit 없이 DEGRADED
# ─────────────────────────────────────────────────────────────────────────────


class TestGraphEngineConfigFailFast:
    """비정수 파싱 실패 시 서버 전체가 죽지 않고 DEGRADED로 격하되는지 검증."""

    @pytest.mark.parametrize("broken_env_key", [
        ENV_MAX_TRAVERSAL_DEPTH,
        ENV_MAX_GRAPH_NODES,
        ENV_MIGRATION_NODE_THRESHOLD,
        ENV_MIGRATION_CONCURRENCY_THRESHOLD,
    ])
    def test_invalid_int_degrades_subsystem_not_crash(
        self,
        broken_env_key: str,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """비정수 환경 변수가 들어와도 SystemExit 없이 GRAPH_ENGINE이 DEGRADED된다."""
        monkeypatch.setenv(broken_env_key, "not-a-valid-integer")

        with caplog.at_level(logging.ERROR, logger=_CONFIG_VALIDATOR_LOGGER):
            # 서버 전체가 죽으면 안 된다 — SystemExit가 발생해서는 절대 안 됨
            cfg = GraphEngineConfig.from_env()

        # 서브시스템 비활성화 (DEGRADED) 확인
        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is False, (
            f"[{broken_env_key}] 비정수 값에도 서브시스템이 DEGRADED되지 않았습니다."
        )

        # SUBSYSTEM HARD FAILURE ERROR 로그가 출력되어야 함
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert error_records, (
            f"[{broken_env_key}] 비정수 파싱 실패 시 ERROR 로그가 출력되지 않았습니다."
        )

    def test_invalid_int_does_not_raise_system_exit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """비정수 환경 변수가 들어와도 SystemExit(1)이 발생하지 않는다."""
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "NOT_AN_INT")

        try:
            cfg = GraphEngineConfig.from_env()
        except SystemExit:
            pytest.fail(
                "GraphEngineConfig.from_env()가 비정수 입력에서 SystemExit를 발생시켰습니다. "
                "이는 Subsystem Fail-fast 정책 위반입니다 (서버 전체가 다운됩니다)."
            )

        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Clamping 검증 — 범위 초과·미만 정수는 Clamp + WARNING 로그
#
# 4개 정수 환경 변수 × 2방향(상한초과/하한미만) = 8케이스 전수 파라미터화.
# 각 케이스에서 Clamping 결과값 + WARNING 로그 출력 여부를 모두 검증한다.
# ─────────────────────────────────────────────────────────────────────────────

# Clamping 파라미터 테이블
# (env_key, 주입값, 기대 clamped값, cfg 속성명, clamp_direction)
_CLAMP_ABOVE_MAX_CASES = [
    (
        ENV_MAX_TRAVERSAL_DEPTH,
        str(MAX_TRAVERSAL_DEPTH_RANGE.max + 10),
        MAX_TRAVERSAL_DEPTH_RANGE.max,
        "max_traversal_depth",
        "above_max",
    ),
    (
        ENV_MAX_GRAPH_NODES,
        str(MAX_GRAPH_NODES_RANGE.max + 500),
        MAX_GRAPH_NODES_RANGE.max,
        "max_graph_nodes",
        "above_max",
    ),
    (
        ENV_MIGRATION_NODE_THRESHOLD,
        str(MIGRATION_NODE_THRESHOLD_RANGE.max + 10000),
        MIGRATION_NODE_THRESHOLD_RANGE.max,
        "migration_node_threshold",
        "above_max",
    ),
    (
        ENV_MIGRATION_CONCURRENCY_THRESHOLD,
        str(MIGRATION_CONCURRENCY_THRESHOLD_RANGE.max + 50),
        MIGRATION_CONCURRENCY_THRESHOLD_RANGE.max,
        "migration_concurrency_threshold",
        "above_max",
    ),
]

_CLAMP_BELOW_MIN_CASES = [
    (
        ENV_MAX_TRAVERSAL_DEPTH,
        str(MAX_TRAVERSAL_DEPTH_RANGE.min - 1),
        MAX_TRAVERSAL_DEPTH_RANGE.min,
        "max_traversal_depth",
        "below_min",
    ),
    (
        ENV_MAX_GRAPH_NODES,
        str(MAX_GRAPH_NODES_RANGE.min - 1),
        MAX_GRAPH_NODES_RANGE.min,
        "max_graph_nodes",
        "below_min",
    ),
    (
        ENV_MIGRATION_NODE_THRESHOLD,
        str(MIGRATION_NODE_THRESHOLD_RANGE.min - 1),
        MIGRATION_NODE_THRESHOLD_RANGE.min,
        "migration_node_threshold",
        "below_min",
    ),
    (
        ENV_MIGRATION_CONCURRENCY_THRESHOLD,
        str(MIGRATION_CONCURRENCY_THRESHOLD_RANGE.min - 1),
        MIGRATION_CONCURRENCY_THRESHOLD_RANGE.min,
        "migration_concurrency_threshold",
        "below_min",
    ),
]

_CLAMP_ALL_CASES = _CLAMP_ABOVE_MAX_CASES + _CLAMP_BELOW_MIN_CASES


class TestGraphEngineConfigClamping:
    """범위 초과·미만 값이 Clamping되고 WARNING 로그가 출력되는지 검증.

    각 정수 환경 변수에 대해:
      * 상한선을 초과하는 값 → max 값으로 Clamping + WARNING 로그
      * 하한선 미만인 값    → min 값으로 Clamping + WARNING 로그
      * 서브시스템은 여전히 정상(ok=True) 상태 유지
    """

    @pytest.mark.parametrize(
        "env_key, injected_value, expected_clamped, cfg_attr, direction",
        _CLAMP_ALL_CASES,
        ids=[
            f"{env_key.split('_')[-1][:8]}_{direction}"
            for env_key, _, _, _, direction in _CLAMP_ALL_CASES
        ],
    )
    def test_clamping_corrects_value_and_emits_warning(
        self,
        env_key: str,
        injected_value: str,
        expected_clamped: int,
        cfg_attr: str,
        direction: str,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """각 정수 환경변수에 대해 Clamping 보정 + WARNING 로그를 모두 검증한다."""
        # given: 범위를 벗어나는 값을 주입
        monkeypatch.setenv(env_key, injected_value)

        # when: 설정을 로드
        with caplog.at_level(logging.WARNING, logger=_CONFIG_VALIDATOR_LOGGER):
            cfg = GraphEngineConfig.from_env()

        # then 1: 설정 값이 기대하는 경계값으로 Clamping 되었는지
        actual = getattr(cfg, cfg_attr)
        assert actual == expected_clamped, (
            f"[{env_key}][{direction}] Clamping 실패: "
            f"주입={injected_value}, 기대={expected_clamped}, 실제={actual}"
        )

        # then 2: Clamping 발생 시 서브시스템은 정상 상태 유지 (DEGRADED 아님)
        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True, (
            f"[{env_key}][{direction}] Clamping 후 서브시스템이 DEGRADED되었습니다. "
            "Clamping은 정상 복구이므로 서브시스템은 활성 상태여야 합니다."
        )

        # then 3: WARNING 로그가 남았고, 환경 변수 이름이 포함되어 있는지
        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and env_key in r.getMessage()
        ]
        assert warning_records, (
            f"[{env_key}][{direction}] Clamping 발생 시 env_key='{env_key}'가 포함된 "
            "WARNING 로그가 존재해야 합니다. 로그 회귀가 의심됩니다."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. DEGRADED 상태가 HealthRegistry.is_ok()에 올바르게 반영되는지 검증
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthRegistryIntegration:
    """HealthRegistry SSOT 인터페이스 계약 검증.

    isolated_registry 픽스처를 사용하여 각 테스트마다 싱글톤 상태를 초기화한다.
    이를 통해 테스트 실행 순서에 관계없이 독립적인 결과를 보장한다.
    """

    def test_is_ok_returns_true_when_subsystem_healthy(
        self, isolated_registry: HealthRegistry
    ) -> None:
        """정상 기동 시 HealthRegistry.is_ok(GRAPH_ENGINE)는 True를 반환해야 한다."""
        isolated_registry.report(Subsystem.GRAPH_ENGINE.value, SubsystemStatus.HEALTHY)

        assert isolated_registry.is_ok(Subsystem.GRAPH_ENGINE) is True

    def test_is_ok_returns_false_when_subsystem_degraded(
        self, isolated_registry: HealthRegistry
    ) -> None:
        """DEGRADED 등록 시 HealthRegistry.is_ok(GRAPH_ENGINE)는 False를 반환해야 한다."""
        isolated_registry.report(Subsystem.GRAPH_ENGINE.value, SubsystemStatus.DEGRADED)

        assert isolated_registry.is_ok(Subsystem.GRAPH_ENGINE) is False

    def test_is_ok_returns_true_when_not_registered_default_mode(
        self, isolated_registry: HealthRegistry
    ) -> None:
        """미등록 서브시스템은 strict=False(기본) 시 True를 반환해야 한다."""
        # isolated_registry는 초기화 직후 상태이므로 어떤 키도 등록되지 않은 상태
        assert isolated_registry.is_ok("non_existent_subsystem_xyz") is True

    def test_is_ok_returns_false_when_not_registered_strict_mode(
        self, isolated_registry: HealthRegistry
    ) -> None:
        """미등록 서브시스템은 strict=True 시 False를 반환해야 한다."""
        assert isolated_registry.is_ok("non_existent_subsystem_xyz", strict=True) is False

    def test_is_ok_accepts_string_key_directly(
        self, isolated_registry: HealthRegistry
    ) -> None:
        """str 키로도 직접 is_ok()를 호출할 수 있어야 한다."""
        key = Subsystem.GRAPH_ENGINE.value  # "graph_engine"
        isolated_registry.report(key, SubsystemStatus.HEALTHY)

        assert isolated_registry.is_ok(key) is True

    def test_is_ok_raises_type_error_on_invalid_type(
        self, isolated_registry: HealthRegistry
    ) -> None:
        """str 및 Enum이 아닌 타입 전달 시 TypeError를 발생시켜야 한다."""
        with pytest.raises(TypeError, match="Unsupported subsystem type"):
            isolated_registry.is_ok(12345)  # type: ignore[arg-type]

    def test_healthy_to_degraded_transition(
        self, isolated_registry: HealthRegistry
    ) -> None:
        """HEALTHY → DEGRADED 전환 시 is_ok()가 즉시 False를 반환해야 한다."""
        isolated_registry.report(Subsystem.GRAPH_ENGINE.value, SubsystemStatus.HEALTHY)
        assert isolated_registry.is_ok(Subsystem.GRAPH_ENGINE) is True

        isolated_registry.report(Subsystem.GRAPH_ENGINE.value, SubsystemStatus.DEGRADED)
        assert isolated_registry.is_ok(Subsystem.GRAPH_ENGINE) is False

    def test_precomputed_summary_avoids_repeated_get_summary(
        self, isolated_registry: HealthRegistry
    ) -> None:
        """precomputed_summary를 전달하면 내부 get_summary() 호출 없이 판정이 이루어진다."""
        isolated_registry.report(Subsystem.GRAPH_ENGINE.value, SubsystemStatus.HEALTHY)
        snapshot = isolated_registry.get_summary()

        # 이후 상태가 바뀌어도 snapshot 기준으로 판정되어야 함
        isolated_registry.report(Subsystem.GRAPH_ENGINE.value, SubsystemStatus.DEGRADED)
        assert isolated_registry.is_ok(
            Subsystem.GRAPH_ENGINE,
            precomputed_summary=snapshot,
        ) is True  # snapshot은 변경 전이므로 True


# ─────────────────────────────────────────────────────────────────────────────
# 5. 복합 시나리오 — 일부 설정만 깨진 경우
# ─────────────────────────────────────────────────────────────────────────────


class TestGraphEngineConfigMixedScenario:
    """일부는 유효하고 일부는 무효한 환경 변수가 혼재할 때의 동작 검증."""

    def test_one_invalid_int_with_others_valid_still_degrades(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """정수 환경 변수 중 하나라도 파싱 실패하면 서브시스템 전체가 DEGRADED된다."""
        # 나머지는 유효한 범위 내 값 — 단 하나만 INVALID
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "INVALID")
        monkeypatch.setenv(ENV_MAX_GRAPH_NODES, "500")
        monkeypatch.setenv(ENV_MIGRATION_NODE_THRESHOLD, "10000")
        monkeypatch.setenv(ENV_MIGRATION_CONCURRENCY_THRESHOLD, "10")

        cfg = GraphEngineConfig.from_env()

        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is False

    def test_all_valid_with_db_url_set_remains_healthy(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """모든 정수 설정이 유효하고 GRAPH_DB_URL이 설정되어도 서브시스템은 정상이어야 한다."""
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, "3")
        monkeypatch.setenv(ENV_MAX_GRAPH_NODES, "500")
        monkeypatch.setenv(ENV_MIGRATION_NODE_THRESHOLD, "10000")
        monkeypatch.setenv(ENV_MIGRATION_CONCURRENCY_THRESHOLD, "10")
        # 보안: 실제 DB URL 값을 하드코딩하지 않음 — 형식 확인용 더미 문자열 사용
        monkeypatch.setenv(ENV_DB_URL, "bolt://localhost:7687")

        cfg = GraphEngineConfig.from_env()

        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True
        # 보안: DB URL 값 자체는 로그 검증 대상이 아님 (크리덴셜 노출 절대 금지)

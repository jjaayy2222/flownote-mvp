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
  2. 범위 초과 값은 Clamping되고 WARNING 로그가 출력되는지 확인.
  3. GRAPH_DB_URL이 없거나 비어있어도 INFO 로그만 남기고 서버가 정상 기동되는지
     확인.
  4. HealthRegistry.is_ok()가 subsystem_ok 상태를 올바르게 반영하는지 확인.

보안 원칙:
  - DB URL 값 자체를 로그에서 검증하거나 하드코딩하지 않는다.
  - 테스트 환경 격리: monkeypatch를 통해 환경 변수 직접 주입/제거한다.
"""

from __future__ import annotations

import pytest

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
from backend.core.config_validator import GraphEngineConfig, Subsystem


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼: 깨끗한 환경 변수 상태 보장 (그래프 관련 변수 모두 제거)
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

    def test_empty_db_url_does_not_degrade_subsystem(self, caplog: pytest.LogCaptureFixture) -> None:
        """GRAPH_DB_URL 미설정은 INFO 로그만 남기고 서브시스템을 DEGRADED하지 않는다."""
        import logging

        with caplog.at_level(logging.INFO, logger="backend.core.config_validator"):
            cfg = GraphEngineConfig.from_env()

        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True
        # INFO 로그에 ENV key 이름이 포함되어야 함 (URL 값 자체는 금지)
        assert any(ENV_DB_URL in record.message for record in caplog.records)
        # DB URL 값(기본 빈 문자열)은 로그에 노출되면 안 됨
        assert DEFAULT_DB_URL not in "".join(
            r.message for r in caplog.records if DEFAULT_DB_URL
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
        import logging

        monkeypatch.setenv(broken_env_key, "not-a-valid-integer")

        with caplog.at_level(logging.ERROR, logger="backend.core.config_validator"):
            # 서버 전체가 죽으면 안 된다 — SystemExit가 발생해서는 절대 안 됨
            cfg = GraphEngineConfig.from_env()

        # 서브시스템 비활성화 (DEGRADED) 확인
        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is False, (
            f"[{broken_env_key}] 비정수 값에도 서브시스템이 DEGRADED되지 않았습니다."
        )

        # SUBSYSTEM HARD FAILURE 로그가 출력되어야 함
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

        # pytest.raises로 SystemExit가 발생하지 않음을 명시적으로 검증
        try:
            cfg = GraphEngineConfig.from_env()
        except SystemExit:
            pytest.fail(
                "GraphEngineConfig.from_env()가 비정수 입력에서 SystemExit를 발생시켰습니다. "
                "이는 Subsystem Fail-fast 정책 위반입니다 (서버 전체가 다운됩니다)."
            )

        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Clamping 검증 — 범위 초과 정수는 Clamp + WARNING
# ─────────────────────────────────────────────────────────────────────────────


class TestGraphEngineConfigClamping:
    """범위 초과 값이 Clamping되고 WARNING 로그가 출력되는지 검증."""

    def test_traversal_depth_above_max_is_clamped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """MAX_TRAVERSAL_DEPTH 범위 초과 시 상한선(max)으로 Clamping된다."""
        import logging

        above_max = MAX_TRAVERSAL_DEPTH_RANGE.max + 10
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, str(above_max))

        with caplog.at_level(logging.WARNING, logger="backend.core.config_validator"):
            cfg = GraphEngineConfig.from_env()

        assert cfg.max_traversal_depth == MAX_TRAVERSAL_DEPTH_RANGE.max
        # Clamping 발생 → 서브시스템은 정상 상태 유지 (DEGRADED 아님)
        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True
        # WARNING 로그에 ENV 키 이름이 포함되어야 함
        assert any(ENV_MAX_TRAVERSAL_DEPTH in r.message for r in caplog.records)

    def test_traversal_depth_below_min_is_clamped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """MAX_TRAVERSAL_DEPTH 범위 미만 시 하한선(min)으로 Clamping된다."""
        import logging

        below_min = MAX_TRAVERSAL_DEPTH_RANGE.min - 1
        monkeypatch.setenv(ENV_MAX_TRAVERSAL_DEPTH, str(below_min))

        with caplog.at_level(logging.WARNING, logger="backend.core.config_validator"):
            cfg = GraphEngineConfig.from_env()

        assert cfg.max_traversal_depth == MAX_TRAVERSAL_DEPTH_RANGE.min
        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True

    def test_max_graph_nodes_above_max_is_clamped(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """MAX_GRAPH_NODES 범위 초과 시 상한선으로 Clamping된다."""
        above_max = MAX_GRAPH_NODES_RANGE.max + 500
        monkeypatch.setenv(ENV_MAX_GRAPH_NODES, str(above_max))

        cfg = GraphEngineConfig.from_env()

        assert cfg.max_graph_nodes == MAX_GRAPH_NODES_RANGE.max
        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True

    def test_migration_node_threshold_below_min_is_clamped(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """MIGRATION_NODE_THRESHOLD 범위 미만 시 하한선으로 Clamping된다."""
        below_min = MIGRATION_NODE_THRESHOLD_RANGE.min - 1
        monkeypatch.setenv(ENV_MIGRATION_NODE_THRESHOLD, str(below_min))

        cfg = GraphEngineConfig.from_env()

        assert cfg.migration_node_threshold == MIGRATION_NODE_THRESHOLD_RANGE.min
        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True

    def test_migration_concurrency_threshold_above_max_is_clamped(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """MIGRATION_CONCURRENCY_THRESHOLD 범위 초과 시 상한선으로 Clamping된다."""
        above_max = MIGRATION_CONCURRENCY_THRESHOLD_RANGE.max + 50
        monkeypatch.setenv(ENV_MIGRATION_CONCURRENCY_THRESHOLD, str(above_max))

        cfg = GraphEngineConfig.from_env()

        assert cfg.migration_concurrency_threshold == MIGRATION_CONCURRENCY_THRESHOLD_RANGE.max
        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. DEGRADED 상태가 HealthRegistry.is_ok()에 올바르게 반영되는지 검증
# ─────────────────────────────────────────────────────────────────────────────


class TestHealthRegistryIntegration:
    """GraphEngineConfig의 DEGRADED 상태가 HealthRegistry SSOT와 올바르게 연동되는지 검증."""

    def test_is_ok_returns_true_when_subsystem_healthy(self) -> None:
        """정상 기동 시 HealthRegistry.is_ok(GRAPH_ENGINE)는 True를 반환해야 한다."""
        from backend.core.health_registry import HealthRegistry, SubsystemStatus

        registry = HealthRegistry.get_instance()
        # GRAPH_ENGINE을 명시적으로 HEALTHY로 등록
        registry.report(Subsystem.GRAPH_ENGINE.value, SubsystemStatus.HEALTHY)

        assert registry.is_ok(Subsystem.GRAPH_ENGINE) is True

    def test_is_ok_returns_false_when_subsystem_degraded(self) -> None:
        """DEGRADED 등록 시 HealthRegistry.is_ok(GRAPH_ENGINE)는 False를 반환해야 한다."""
        from backend.core.health_registry import HealthRegistry, SubsystemStatus

        registry = HealthRegistry.get_instance()
        registry.report(Subsystem.GRAPH_ENGINE.value, SubsystemStatus.DEGRADED)

        assert registry.is_ok(Subsystem.GRAPH_ENGINE) is False

    def test_is_ok_returns_true_when_not_registered_default_mode(self) -> None:
        """미등록 서브시스템은 strict=False(기본) 시 True를 반환해야 한다."""
        from backend.core.health_registry import HealthRegistry

        registry = HealthRegistry.get_instance()
        # 등록된 적 없는 키 사용
        assert registry.is_ok("non_existent_subsystem_xyz") is True

    def test_is_ok_returns_false_when_not_registered_strict_mode(self) -> None:
        """미등록 서브시스템은 strict=True 시 False를 반환해야 한다."""
        from backend.core.health_registry import HealthRegistry

        registry = HealthRegistry.get_instance()
        assert registry.is_ok("non_existent_subsystem_xyz", strict=True) is False

    def test_is_ok_raises_type_error_on_invalid_type(self) -> None:
        """str 및 Enum이 아닌 타입 전달 시 TypeError를 발생시켜야 한다."""
        from backend.core.health_registry import HealthRegistry

        registry = HealthRegistry.get_instance()
        with pytest.raises(TypeError, match="Unsupported subsystem type"):
            registry.is_ok(12345)  # type: ignore[arg-type]


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
        # 나머지는 유효한 범위 내 값 설정
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
        # 보안: 실제 DB URL 값을 하드코딩하지 않음 — 더미 형식 문자열 사용
        monkeypatch.setenv(ENV_DB_URL, "bolt://localhost:7687")

        cfg = GraphEngineConfig.from_env()

        assert cfg.subsystem_ok[Subsystem.GRAPH_ENGINE] is True
        # 보안: DB URL은 로그 검증 대상이 아님 (값 자체 노출 금지)

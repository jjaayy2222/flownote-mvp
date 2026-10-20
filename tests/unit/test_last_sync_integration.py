# tests/unit/test_last_sync_integration.py

"""
Unit tests for last_sync SyncMapManager integration (#12.3.33).

Covers:
- SyncMapManager.get_latest_sync_time():
  - 매핑 없을 때 None 반환
  - last_synced_at=None인 매핑만 있을 때 None 반환
  - 단일 매핑에서 정확한 시각 반환
  - 여러 매핑 중 가장 최신 시각 반환
  - timezone-aware / naive 혼합 시 안전한 비교
  - tool_type 필터링 적용 시 해당 도구 기준 최신 시각 반환
  - tool_type 필터링 — 해당 도구 매핑이 없을 때 None 반환
- GET /api/sync/status: last_sync 실연동 검증 (SyncMapManager mock)
- GET /api/automation/dashboard/summary: last_sync 실연동 검증 (SyncMapManager mock)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.mcp.sync_map_manager import SyncMapManager, reset_sync_map_manager
from backend.models.external_sync import ExternalFileMapping, ExternalToolType

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_singleton():
    """각 테스트 전후 SyncMapManager 싱글톤 초기화 (테스트 격리)."""
    reset_sync_map_manager()
    yield
    reset_sync_map_manager()


@pytest.fixture
def manager(tmp_path):
    """임시 디렉터리 기반 격리된 SyncMapManager 인스턴스."""
    return SyncMapManager(
        storage_dir=str(tmp_path),
        filename="test_mappings.json",
    )


def _make_mapping(
    internal_id: str,
    external_path: str,
    tool_type: ExternalToolType = ExternalToolType.OBSIDIAN,
    last_synced_at: datetime | None = None,
) -> ExternalFileMapping:
    """테스트용 ExternalFileMapping 헬퍼."""
    m = ExternalFileMapping(
        internal_file_id=internal_id,
        external_path=external_path,
        tool_type=tool_type,
    )
    if last_synced_at is not None:
        m.last_synced_at = last_synced_at
    return m


# ============================================================================
# SyncMapManager.get_latest_sync_time() 단위 테스트
# ============================================================================


class TestGetLatestSyncTime:
    def test_returns_none_when_no_mappings(self, manager):
        """매핑이 없을 때 None을 반환해야 한다."""
        result = manager.get_latest_sync_time()
        assert result is None

    def test_returns_none_when_all_last_synced_at_is_none(self, manager):
        """last_synced_at이 모두 None인 매핑만 있을 때 None을 반환해야 한다.

        ExternalFileMapping.last_synced_at은 default_factory로 항상 datetime을
        갖지만, _mappings에 직접 MagicMock을 삽입하여 None 경로를 검증한다.
        """
        mock_mapping = MagicMock()
        mock_mapping.last_synced_at = None
        mock_mapping.tool_type = ExternalToolType.OBSIDIAN
        manager._mappings["mock-id"] = mock_mapping

        result = manager.get_latest_sync_time()
        assert result is None

    def test_returns_correct_time_for_single_mapping(self, manager):
        """단일 매핑에서 last_synced_at을 그대로 반환해야 한다."""
        dt = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
        mapping = _make_mapping("id-1", "/path/a.md", last_synced_at=dt)
        manager._mappings["id-1"] = mapping

        result = manager.get_latest_sync_time()
        assert result == dt

    def test_returns_latest_among_multiple_mappings(self, manager):
        """여러 매핑 중 가장 최신 last_synced_at을 반환해야 한다."""
        dt_old = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
        dt_new = datetime(2026, 10, 19, 9, 0, 0, tzinfo=timezone.utc)
        dt_mid = datetime(2026, 10, 10, 6, 0, 0, tzinfo=timezone.utc)

        manager._mappings["id-1"] = _make_mapping(
            "id-1", "/a.md", last_synced_at=dt_old
        )
        manager._mappings["id-2"] = _make_mapping(
            "id-2", "/b.md", last_synced_at=dt_new
        )
        manager._mappings["id-3"] = _make_mapping(
            "id-3", "/c.md", last_synced_at=dt_mid
        )

        result = manager.get_latest_sync_time()
        assert result == dt_new

    def test_handles_mixed_aware_and_naive_datetimes(self, manager):
        """timezone-aware/naive 혼합 시 안전하게 최신 시각을 반환해야 한다."""
        dt_naive = datetime(2026, 10, 19, 9, 0, 0)  # naive (UTC로 간주)
        dt_aware = datetime(2026, 10, 19, 8, 0, 0, tzinfo=timezone.utc)  # older

        manager._mappings["id-naive"] = _make_mapping(
            "id-naive", "/a.md", last_synced_at=dt_naive
        )
        manager._mappings["id-aware"] = _make_mapping(
            "id-aware", "/b.md", last_synced_at=dt_aware
        )

        result = manager.get_latest_sync_time()
        # dt_naive(09:00)이 dt_aware(08:00)보다 최신
        assert result == dt_naive

    def test_filters_by_tool_type(self, manager):
        """tool_type 필터링 시 해당 도구 매핑의 최신 시각만 반환해야 한다."""
        dt_obsidian = datetime(2026, 10, 19, 10, 0, 0, tzinfo=timezone.utc)
        dt_notion = datetime(2026, 10, 19, 11, 0, 0, tzinfo=timezone.utc)  # newer

        manager._mappings["id-obs"] = _make_mapping(
            "id-obs", "/obs.md", ExternalToolType.OBSIDIAN, last_synced_at=dt_obsidian
        )
        manager._mappings["id-notion"] = _make_mapping(
            "id-notion",
            "/notion.md",
            ExternalToolType.NOTION,
            last_synced_at=dt_notion,
        )

        # OBSIDIAN 필터만 적용 → notion의 더 최신 시각은 무시
        result = manager.get_latest_sync_time(tool_type=ExternalToolType.OBSIDIAN)
        assert result == dt_obsidian

    def test_returns_none_when_no_matching_tool_type(self, manager):
        """필터링 결과 해당 tool_type 매핑이 없을 때 None을 반환해야 한다."""
        dt = datetime(2026, 10, 19, 10, 0, 0, tzinfo=timezone.utc)
        manager._mappings["id-obs"] = _make_mapping(
            "id-obs", "/obs.md", ExternalToolType.OBSIDIAN, last_synced_at=dt
        )

        result = manager.get_latest_sync_time(tool_type=ExternalToolType.NOTION)
        assert result is None


# ============================================================================
# GET /sync/status — last_sync 실연동 검증
# ============================================================================


class TestSyncStatusLastSync:
    @pytest.fixture
    def client(self):
        from backend.main import app

        return TestClient(app)

    def test_last_sync_is_none_when_no_mappings(self, client):
        """매핑이 없을 때 last_sync가 null이어야 한다."""
        mock_manager = MagicMock(spec=SyncMapManager)
        mock_manager.get_latest_sync_time.return_value = None

        with patch(
            "backend.api.endpoints.sync.get_sync_map_manager",
            return_value=mock_manager,
        ):
            response = client.get("/api/sync/status")

        assert response.status_code == 200
        assert response.json()["last_sync"] is None

    def test_last_sync_is_iso_string_when_mapping_exists(self, client):
        """매핑이 있을 때 last_sync가 ISO 형식 문자열이어야 한다."""
        dt = datetime(2026, 10, 19, 9, 0, 0, tzinfo=timezone.utc)
        mock_manager = MagicMock(spec=SyncMapManager)
        mock_manager.get_latest_sync_time.return_value = dt

        with patch(
            "backend.api.endpoints.sync.get_sync_map_manager",
            return_value=mock_manager,
        ):
            response = client.get("/api/sync/status")

        assert response.status_code == 200
        last_sync_val = response.json()["last_sync"]
        assert last_sync_val is not None
        # ISO 8601 파싱 가능 검증
        parsed = datetime.fromisoformat(last_sync_val)
        assert parsed.year == 2026


# ============================================================================
# GET /automation/dashboard/summary — last_sync 실연동 검증
# ============================================================================


class TestDashboardSummaryLastSync:
    @pytest.fixture
    def client(self):
        from backend.main import app

        return TestClient(app)

    def test_last_sync_is_none_when_no_mappings(self, client):
        """매핑이 없을 때 대시보드 last_sync가 null이어야 한다."""
        mock_manager = MagicMock(spec=SyncMapManager)
        mock_manager.get_latest_sync_time.return_value = None

        with patch(
            "backend.api.endpoints.automation.get_sync_map_manager",
            return_value=mock_manager,
        ):
            response = client.get("/api/automation/dashboard/summary")

        assert response.status_code == 200
        assert response.json()["last_sync"] is None

    def test_last_sync_is_iso_string_when_mapping_exists(self, client):
        """매핑이 있을 때 대시보드 last_sync가 ISO 형식 문자열이어야 한다."""
        dt = datetime(2026, 10, 19, 7, 30, 0, tzinfo=timezone.utc)
        mock_manager = MagicMock(spec=SyncMapManager)
        mock_manager.get_latest_sync_time.return_value = dt

        with patch(
            "backend.api.endpoints.automation.get_sync_map_manager",
            return_value=mock_manager,
        ):
            response = client.get("/api/automation/dashboard/summary")

        assert response.status_code == 200
        last_sync_val = response.json()["last_sync"]
        assert last_sync_val is not None
        parsed = datetime.fromisoformat(last_sync_val)
        assert parsed.hour == 7
        assert parsed.minute == 30


# ============================================================================
# GET /automation/dashboard/summary — active_rules / pending_tasks 집계 검증
# ============================================================================


class TestDashboardSummaryActiveRulesAndPendingTasks:
    """DashboardSummary.active_rules 및 pending_tasks 실연동 검증."""

    @pytest.fixture
    def client(self):
        from backend.main import app

        return TestClient(app)

    def _make_mock_rule(self, *, is_active: bool):
        """AutomationRule mock 헬퍼."""
        rule = MagicMock()
        rule.is_active = is_active
        return rule

    def _make_mock_log(self, status: str):
        """AutomationLog mock 헬퍼."""
        log = MagicMock()
        log.status = status
        return log

    def test_active_rules_counts_only_active(self, client):
        """is_active=True인 규칙만 active_rules에 반영되어야 한다."""
        rules = [
            self._make_mock_rule(is_active=True),
            self._make_mock_rule(is_active=False),
            self._make_mock_rule(is_active=True),
        ]
        mock_map_manager = MagicMock(spec=SyncMapManager)
        mock_map_manager.get_latest_sync_time.return_value = None

        with (
            patch(
                "backend.api.endpoints.automation.automation_manager.get_automation_rules",
                return_value=rules,
            ),
            patch(
                "backend.api.endpoints.automation.automation_manager.get_automation_logs",
                return_value=[],
            ),
            patch(
                "backend.api.endpoints.automation.automation_manager.get_reclassification_history",
                return_value=[],
            ),
            patch(
                "backend.api.endpoints.automation.get_sync_map_manager",
                return_value=mock_map_manager,
            ),
        ):
            response = client.get("/api/automation/dashboard/summary")

        assert response.status_code == 200
        assert response.json()["active_rules"] == 2

    def test_pending_tasks_sums_running_and_pending_logs(self, client):
        """RUNNING + PENDING 로그 합산이 pending_tasks에 반영되어야 한다."""
        from backend.models.automation import AutomationStatus

        mock_map_manager = MagicMock(spec=SyncMapManager)
        mock_map_manager.get_latest_sync_time.return_value = None

        def _get_logs_by_status(limit=100, task_type=None, status=None):
            if status == AutomationStatus.RUNNING:
                return [self._make_mock_log("running")] * 2
            if status == AutomationStatus.PENDING:
                return [self._make_mock_log("pending")] * 3
            # COMPLETED 등 나머지: 빈 리스트
            return []

        with (
            patch(
                "backend.api.endpoints.automation.automation_manager.get_automation_rules",
                return_value=[],
            ),
            patch(
                "backend.api.endpoints.automation.automation_manager.get_automation_logs",
                side_effect=_get_logs_by_status,
            ),
            patch(
                "backend.api.endpoints.automation.automation_manager.get_reclassification_history",
                return_value=[],
            ),
            patch(
                "backend.api.endpoints.automation.get_sync_map_manager",
                return_value=mock_map_manager,
            ),
        ):
            response = client.get("/api/automation/dashboard/summary")

        assert response.status_code == 200
        assert response.json()["pending_tasks"] == 5  # 2 running + 3 pending

    def test_zero_active_rules_when_all_inactive(self, client):
        """모든 규칙이 비활성화일 때 active_rules가 0이어야 한다."""
        rules = [
            self._make_mock_rule(is_active=False),
            self._make_mock_rule(is_active=False),
        ]
        mock_map_manager = MagicMock(spec=SyncMapManager)
        mock_map_manager.get_latest_sync_time.return_value = None

        with (
            patch(
                "backend.api.endpoints.automation.automation_manager.get_automation_rules",
                return_value=rules,
            ),
            patch(
                "backend.api.endpoints.automation.automation_manager.get_automation_logs",
                return_value=[],
            ),
            patch(
                "backend.api.endpoints.automation.automation_manager.get_reclassification_history",
                return_value=[],
            ),
            patch(
                "backend.api.endpoints.automation.get_sync_map_manager",
                return_value=mock_map_manager,
            ),
        ):
            response = client.get("/api/automation/dashboard/summary")

        assert response.status_code == 200
        assert response.json()["active_rules"] == 0
        assert response.json()["pending_tasks"] == 0

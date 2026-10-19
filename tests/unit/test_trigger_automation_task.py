# tests/unit/test_trigger_automation_task.py

"""
Unit tests for Celery Manual Task Trigger Endpoint (#12.3.34).

Covers:
- resolve_celery_task():
  - All 5 AutomationTaskType defaults (reclassification, archiving, reporting, monitoring, maintenance)
  - Specific task_name aliases and case-insensitivity
  - auto_archive / auto-archive alias → auto_archive_tasks 매핑
  - Unknown task_name handling (HTTPException 400 with available list)
  - Unsupported task_type handling (HTTPException 400)
  - 빈 문자열("") 및 공백 task_name 전달 시 400 Bad Request (의도치 않은 파괴적 기본 작업 실행 방지)
- trigger_automation_task():
  - Successful asynchronous dispatch via .delay() (202 Accepted, task_id, status="queued")
  - triggered_at이 UTC timezone-aware datetime인지 검증 (naive datetime 허용 안 함)
  - automation_manager.record_task_trigger() integration (PENDING log record)
  - Celery broker connection error handling (HTTPException 503 Service Unavailable)
  - automation_manager failure resilience (preserves 202 response even if log write fails)
- FastAPI TestClient integration:
  - POST /automation/tasks/trigger with query params
  - Valid task_type with/without task_name
  - auto_archive alias HTTP 레벨 202 응답 검증
  - 빈 task_name 전달 시 400 Bad Request HTTP 응답 검증
  - Invalid task_name (400 Bad Request)
  - Invalid task_type (422 Unprocessable Entity)
  - Broker failure (503 Service Unavailable)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.endpoints.automation import (
    TASK_REGISTRY,
    TaskTriggerResponse,
    resolve_celery_task,
    trigger_automation_task,
)
from backend.main import app
from backend.models.automation import AutomationStatus, AutomationTaskType

# ============================================================================
# 1. resolve_celery_task Unit Tests
# ============================================================================


def test_resolve_celery_task_defaults():
    """각 AutomationTaskType별 기본 태스크 매핑 검증"""
    expected_defaults = {
        AutomationTaskType.RECLASSIFICATION: "daily-reclassify",
        AutomationTaskType.ARCHIVING: "archive-inactive-files",
        AutomationTaskType.REPORTING: "generate-weekly-report",
        AutomationTaskType.MONITORING: "check_sync_status",
        AutomationTaskType.MAINTENANCE: "cleanup_old_logs",
    }

    for task_type, expected_name in expected_defaults.items():
        task_func, task_name = resolve_celery_task(task_type, None)
        assert callable(task_func) or hasattr(task_func, "delay")
        assert task_name == expected_name


def test_resolve_celery_task_aliases():
    """세부 task_name 별칭 및 대소문자/공백 정규화 매핑 검증"""
    test_cases = [
        (AutomationTaskType.RECLASSIFICATION, "weekly", "weekly-reclassify"),
        (AutomationTaskType.RECLASSIFICATION, " DAILY-RECLASSIFY ", "daily-reclassify"),
        (AutomationTaskType.REPORTING, "monthly", "generate-monthly-report"),
        (
            AutomationTaskType.REPORTING,
            "generate-weekly-report",
            "generate-weekly-report",
        ),
        (AutomationTaskType.MONITORING, "health", "check_task_health"),
        (AutomationTaskType.MONITORING, "sync", "check_sync_status"),
        (AutomationTaskType.MAINTENANCE, "backup", "backup_automation_data"),
        (AutomationTaskType.MAINTENANCE, "cleanup", "cleanup_old_logs"),
        (AutomationTaskType.ARCHIVING, "archive", "archive-inactive-files"),
        # auto_archive_tasks 별칭 정식 등록 검증
        (AutomationTaskType.ARCHIVING, "auto_archive", "auto_archive_tasks"),
        (AutomationTaskType.ARCHIVING, "auto-archive", "auto_archive_tasks"),
        (AutomationTaskType.ARCHIVING, " AUTO-ARCHIVE ", "auto_archive_tasks"),
    ]

    for task_type, alias, expected_name in test_cases:
        task_func, resolved_name = resolve_celery_task(task_type, alias)
        assert callable(task_func) or hasattr(task_func, "delay")
        assert resolved_name == expected_name


def test_resolve_celery_task_unknown_task_name():
    """지원되지 않는 task_name 전달 시 400 Bad Request 및 사용 가능한 목록 안내 검증"""
    with pytest.raises(HTTPException) as exc_info:
        resolve_celery_task(AutomationTaskType.RECLASSIFICATION, "unknown_task_xyz")

    assert exc_info.value.status_code == 400
    assert "Unknown task_name 'unknown_task_xyz'" in exc_info.value.detail
    assert "Available task names:" in exc_info.value.detail


def test_resolve_celery_task_unsupported_task_type():
    """등록되지 않은 task_type 전달 시 400 Bad Request 검증"""
    with pytest.raises(HTTPException) as exc_info:
        resolve_celery_task("non_existent_type", None)  # type: ignore

    assert exc_info.value.status_code == 400
    assert "Unsupported automation task type" in exc_info.value.detail


@pytest.mark.parametrize(
    "task_type,empty_task_name",
    [
        # 빈 문자열 및 공백: None(생략)과 달리 의도치 않은 기본 작업 실행 방지를 위해 400 거부
        (AutomationTaskType.ARCHIVING, ""),
        (AutomationTaskType.ARCHIVING, "   "),
        (AutomationTaskType.RECLASSIFICATION, ""),
        (AutomationTaskType.MAINTENANCE, ""),
    ],
)
def test_resolve_celery_task_empty_task_name_rejected(task_type, empty_task_name):
    """
    task_name이 명시적으로 빈 문자열("") 또는 공백만 포함된 경우 400 Bad Request 반환 검증.

    의도: None(파라미터 생략)과 달리, 빈 문자열은 클라이언트의 의도를 알 수 없으므로
    파괴적일 수 있는 기본 작업(아카이브, 로그 삭제 등)을 자동 실행하지 않도록 거부.
    """
    with pytest.raises(HTTPException) as exc_info:
        resolve_celery_task(task_type, empty_task_name)

    assert exc_info.value.status_code == 400
    assert "task_name cannot be empty" in exc_info.value.detail
    assert "Available task names" in exc_info.value.detail


# ============================================================================
# 2. trigger_automation_task Direct Execution Tests
# ============================================================================


def test_trigger_automation_task_success():
    """수동 태스크 트리거 성공 시 .delay() 호출, 202 응답 및 매니저 이력 기록 검증"""
    mock_async_result = MagicMock()
    mock_async_result.id = "celery-mock-id-777"

    mock_celery_task = MagicMock()
    mock_celery_task.delay.return_value = mock_async_result

    with patch.dict(
        TASK_REGISTRY[AutomationTaskType.RECLASSIFICATION],
        {"default": (mock_celery_task, "daily-reclassify")},
    ):
        with patch(
            "backend.api.endpoints.automation.automation_manager.record_task_trigger"
        ) as mock_record:
            response = trigger_automation_task(
                task_type=AutomationTaskType.RECLASSIFICATION,
                task_name=None,
            )

            assert isinstance(response, TaskTriggerResponse)
            assert response.task_id == "celery-mock-id-777"
            assert response.task_type == AutomationTaskType.RECLASSIFICATION
            assert response.task_name == "daily-reclassify"
            assert response.status == "queued"
            assert "successfully triggered" in response.message

            # triggered_at: UTC timezone-aware datetime 검증
            # naive datetime(tzinfo=None)은 서버 로컬 시간 의존으로 국제화 오류 원인이 되므로 허용 안 함
            assert isinstance(response.triggered_at, datetime)
            assert response.triggered_at.tzinfo is not None, (
                "triggered_at must be timezone-aware (UTC). "
                "Got naive datetime without tzinfo."
            )
            assert (
                response.triggered_at.tzinfo == timezone.utc
            ), f"triggered_at must be UTC, got tzinfo={response.triggered_at.tzinfo}"

            mock_celery_task.delay.assert_called_once()
            mock_record.assert_called_once_with(
                task_type=AutomationTaskType.RECLASSIFICATION,
                task_name="daily-reclassify",
                celery_task_id="celery-mock-id-777",
                status=AutomationStatus.PENDING,
                details={
                    "trigger": "manual_api",
                    "triggered_at": response.triggered_at.isoformat(),
                },
            )


def test_trigger_automation_task_broker_unavailable():
    """Celery 브로커 연결 실패 시 503 Service Unavailable 오류 발생 검증"""
    mock_celery_task = MagicMock()
    mock_celery_task.delay.side_effect = ConnectionError(
        "Cannot connect to Redis broker"
    )

    with patch.dict(
        TASK_REGISTRY[AutomationTaskType.ARCHIVING],
        {"default": (mock_celery_task, "archive-inactive-files")},
    ):
        with pytest.raises(HTTPException) as exc_info:
            trigger_automation_task(
                task_type=AutomationTaskType.ARCHIVING,
                task_name=None,
            )

        assert exc_info.value.status_code == 503
        assert "Celery task broker is unavailable" in exc_info.value.detail


def test_trigger_automation_task_manager_error_resilience():
    """automation_manager 기록 실패 시에도 태스크 트리거 202 응답이 보존되는지 검증"""
    mock_async_result = MagicMock()
    mock_async_result.id = "celery-id-resilience"

    mock_celery_task = MagicMock()
    mock_celery_task.delay.return_value = mock_async_result

    with patch.dict(
        TASK_REGISTRY[AutomationTaskType.MONITORING],
        {"default": (mock_celery_task, "check_sync_status")},
    ):
        with patch(
            "backend.api.endpoints.automation.automation_manager.record_task_trigger",
            side_effect=OSError("Disk full"),
        ):
            response = trigger_automation_task(
                task_type=AutomationTaskType.MONITORING,
                task_name=None,
            )

            assert response.task_id == "celery-id-resilience"
            assert response.status == "queued"


# ============================================================================
# 3. FastAPI TestClient HTTP Integration Tests
# ============================================================================


def test_http_trigger_reclassification_default():
    """HTTP POST /automation/tasks/trigger 기본 파라미터 202 응답 검증"""
    client = TestClient(app)

    mock_async_result = MagicMock()
    mock_async_result.id = "http-task-reclass-1"

    with patch(
        "backend.celery_app.tasks.reclassification.daily_reclassify_tasks.delay",
        return_value=mock_async_result,
    ), patch("backend.api.endpoints.automation.automation_manager.record_task_trigger"):
        response = client.post("/automation/tasks/trigger?task_type=reclassification")
        assert response.status_code == 202
        data = response.json()
        assert data["task_id"] == "http-task-reclass-1"
        assert data["task_type"] == "reclassification"
        assert data["task_name"] == "daily-reclassify"
        assert data["status"] == "queued"
        assert "triggered_at" in data
        # UTC 오프셋이 ISO 8601 문자열에 포함되는지 검증 (+00:00 또는 Z)
        triggered_at_str = data["triggered_at"]
        assert "+00:00" in triggered_at_str or triggered_at_str.endswith(
            "Z"
        ), f"triggered_at must be UTC ISO 8601, got: {triggered_at_str}"


def test_http_trigger_reporting_with_task_name():
    """HTTP POST /automation/tasks/trigger 세부 task_name 지정 202 응답 검증"""
    client = TestClient(app)

    mock_async_result = MagicMock()
    mock_async_result.id = "http-task-report-monthly"

    with patch(
        "backend.celery_app.tasks.reporting.generate_monthly_report.delay",
        return_value=mock_async_result,
    ), patch("backend.api.endpoints.automation.automation_manager.record_task_trigger"):
        response = client.post(
            "/automation/tasks/trigger?task_type=reporting&task_name=monthly"
        )
        assert response.status_code == 202
        data = response.json()
        assert data["task_id"] == "http-task-report-monthly"
        assert data["task_type"] == "reporting"
        assert data["task_name"] == "generate-monthly-report"


def test_http_trigger_invalid_task_name():
    """HTTP POST /automation/tasks/trigger 잘못된 task_name 시 400 반환 검증"""
    client = TestClient(app)

    response = client.post(
        "/automation/tasks/trigger?task_type=reclassification&task_name=invalid_foo"
    )
    assert response.status_code == 400
    assert "Unknown task_name 'invalid_foo'" in response.json()["detail"]


def test_http_trigger_invalid_task_type():
    """HTTP POST /automation/tasks/trigger 잘못된 task_type 시 422 반환 검증"""
    client = TestClient(app)

    response = client.post("/automation/tasks/trigger?task_type=invalid_type")
    assert response.status_code == 422


def test_http_trigger_broker_failure():
    """HTTP POST /automation/tasks/trigger 브로커 연결 실패 시 503 반환 검증"""
    client = TestClient(app)

    with patch(
        "backend.celery_app.tasks.maintenance.cleanup_old_logs.delay",
        side_effect=ConnectionError("Redis connection refused"),
    ):
        response = client.post("/automation/tasks/trigger?task_type=maintenance")
        assert response.status_code == 503
        assert "Celery task broker is unavailable" in response.json()["detail"]


# ============================================================================
# 4. 보강: Archiving alias 및 빈 task_name HTTP 레벨 검증
# ============================================================================


def test_http_trigger_archiving_auto_archive_alias():
    """auto_archive 별칭으로 HTTP 트리거 시 auto_archive_tasks 태스크 실행 202 검증"""
    client = TestClient(app)

    mock_async_result = MagicMock()
    mock_async_result.id = "http-task-auto-archive"

    with patch(
        "backend.celery_app.tasks.archiving.auto_archive_tasks.delay",
        return_value=mock_async_result,
    ), patch("backend.api.endpoints.automation.automation_manager.record_task_trigger"):
        response = client.post(
            "/automation/tasks/trigger?task_type=archiving&task_name=auto_archive"
        )
        assert response.status_code == 202
        data = response.json()
        assert data["task_id"] == "http-task-auto-archive"
        assert data["task_name"] == "auto_archive_tasks"
        # UTC 오프셋 포함 여부 검증
        triggered_at_str = data["triggered_at"]
        assert "+00:00" in triggered_at_str or triggered_at_str.endswith(
            "Z"
        ), f"triggered_at must be UTC ISO 8601, got: {triggered_at_str}"


@pytest.mark.parametrize(
    "task_type,empty_task_name",
    [
        ("archiving", ""),
        ("archiving", "   "),
        ("maintenance", ""),
        ("reclassification", ""),
    ],
)
def test_http_trigger_empty_task_name_rejected(task_type, empty_task_name):
    """
    HTTP 레벨에서 task_name이 빈 문자열 또는 공백만 전달된 경우 400 Bad Request 반환 검증.

    의도: None(파라미터 생략)과 달리 빈 문자열이 전달된 경우,
    파괴적일 수 있는 기본 작업(아카이브, 로그 삭제 등)이 자동 실행되지 않아야 함.
    """
    client = TestClient(app)

    response = client.post(
        f"/automation/tasks/trigger?task_type={task_type}&task_name={empty_task_name}"
    )
    assert response.status_code == 400, (
        f"Expected 400 for task_type={task_type!r} task_name={empty_task_name!r}, "
        f"got {response.status_code}"
    )
    assert "task_name cannot be empty" in response.json()["detail"]

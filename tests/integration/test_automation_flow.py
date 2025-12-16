# tests/integration/test_automation_flow.py

"""
자동화 기능 통합 테스트
- AutomationManager 서비스와 파일 시스템 간의 통합 테스트
- Celery 작업 결과(로그 파일) 조회 플로우 검증
- API 엔드포인트 동작 검증
"""

import pytest
import json
import uuid
import warnings
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.automation import (
    AutomationLog,
    AutomationTaskType,
    AutomationStatus,
    ReclassificationRecord,
)

# 테스트용 클라이언트
client = TestClient(app)

# Schema Constants
REQUIRED_ERROR_KEYS = {"detail"}
REQUIRED_LOG_LIST_KEYS = {"total", "logs"}


@pytest.fixture
def mock_automation_env(tmp_path):
    """
    테스트를 위한 격리된 파일 환경 설정
    unittest.mock.patch를 사용하여 모듈 레벨 상수를 임시 경로로 교체
    """
    # 1. 임시 디렉토리 생성
    data_dir = tmp_path / "data"
    log_dir = data_dir / "automation_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 2. AutomationManager의 모듈 상수 Patch
    # backend.services.automation_manager 모듈의 상수들을 교체

    log_file = log_dir / "automation.jsonl"
    reclass_file = log_dir / "reclassification.jsonl"
    archive_file = log_dir / "archiving.jsonl"

    with patch("backend.services.automation_manager.AUTO_LOG_FILE", log_file), patch(
        "backend.services.automation_manager.RECLASS_LOG_FILE", reclass_file
    ), patch("backend.services.automation_manager.ARCHIVE_LOG_FILE", archive_file):

        yield {
            "log_file": log_file,
            "reclass_file": reclass_file,
            "archive_file": archive_file,
        }


@pytest.fixture
def seeded_logs(mock_automation_env):
    """
    테스트용 로그 데이터 생성
    """
    logs = []
    # 1. 아카이브 실패 로그 (과거 - 1시간 전)
    logs.append(
        AutomationLog(
            log_id=str(uuid.uuid4()),
            task_type=AutomationTaskType.ARCHIVING,
            task_name="auto-archive",
            celery_task_id="task-2",
            status=AutomationStatus.FAILED,
            files_processed=5,
            started_at=datetime.now() - timedelta(hours=1),
            details={"error": "Permission denied"},
        )
    )

    # 2. 재분류 성공 로그 (최신 - 현재)
    logs.append(
        AutomationLog(
            log_id=str(uuid.uuid4()),
            task_type=AutomationTaskType.RECLASSIFICATION,
            task_name="daily-reclassify",
            celery_task_id="task-1",
            status=AutomationStatus.COMPLETED,
            files_processed=10,
            files_updated=2,
            started_at=datetime.now(),
        )
    )

    log_file = mock_automation_env["log_file"]
    with open(log_file, "w", encoding="utf-8") as f:
        for log in logs:
            f.write(log.model_dump_json() + "\n")

    # 검증 로직에서는 최신이 먼저 오는지 확인하므로
    # logs 리스트 자체를 반환할 때는 생성 순서(과거->최신)대로 반환됨.
    # 테스트 코드에서 seeded_logs[1]이 최신임.
    return logs


class TestAutomationFlow:
    """자동화 플로우 통합 테스트"""

    def _validate_schema_keys(self, data: dict, required_keys: set, context: str):
        """
        공통 스키마 키 검증 헬퍼
        - 필수 키 존재 여부 검증 (Contract)
        - 추가 키 발견 시 경고 발생 (Visibility using warnings)
        """
        assert required_keys.issubset(
            data.keys()
        ), f"Missing keys in {context}. Expected {required_keys}"

        extra = set(data.keys()) - required_keys
        if extra:
            warnings.warn(f"Extra keys found in {context}: {extra}", UserWarning)

    def _assert_error_schema(self, data: dict):
        """에러 응답 스키마 검증 헬퍼"""
        assert isinstance(data, dict)
        self._validate_schema_keys(data, REQUIRED_ERROR_KEYS, "error response")
        assert isinstance(data["detail"], str)

    def _assert_log_list_schema(self, data: dict):
        """로그 목록 응답 스키마 검증 헬퍼"""
        assert isinstance(data, dict)
        self._validate_schema_keys(data, REQUIRED_LOG_LIST_KEYS, "log list response")
        assert isinstance(data["total"], int)
        assert isinstance(data["logs"], list)

    def test_get_logs_flow(self, mock_automation_env, seeded_logs):
        """
        [Flow] 로그 조회 통합 테스트
        상황: Celery 작업이 실행되어 로그가 파일에 저장됨
        동작: API를 통해 로그 목록 조회
        검증: 저장된 2개의 로그가 정확히 반환되는지 확인
        """
        response = client.get("/api/automation/logs")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2

        # 최신순 정렬 확인 (seeded_logs[0]이 더 최신)
        assert data["logs"][0]["task_type"] == AutomationTaskType.RECLASSIFICATION.value
        assert data["logs"][1]["task_type"] == AutomationTaskType.ARCHIVING.value

    def test_get_log_detail_flow(self, mock_automation_env, seeded_logs):
        """
        [Flow] 로그 상세 조회 통합 테스트
        """
        target_log = seeded_logs[1]  # 최신 로그 (daily-reclassify)
        log_id = target_log.log_id

        response = client.get(f"/api/automation/logs/{log_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["log_id"] == log_id
        assert data["task_name"] == "daily-reclassify"

    def test_filter_logs_flow(self, mock_automation_env, seeded_logs):
        """
        [Flow] 로그 필터링 통합 테스트
        """
        # Task Type 필터링
        response = client.get("/api/automation/logs", params={"task_type": "archiving"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["logs"][0]["task_type"] == "archiving"

        # Status 필터링
        response = client.get("/api/automation/logs", params={"status": "completed"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["logs"][0]["status"] == "completed"

    def test_reclassification_history_flow(self, mock_automation_env):
        """
        [Flow] 재분류 이력 조회 플로우
        """
        # 데이터 시딩
        records = [
            ReclassificationRecord(
                record_id="rec-1",
                automation_log_id="log-1",
                file_path="/data/test.md",
                old_category="Inbox",
                new_category="Projects",
                confidence_score=0.95,
                processed_at=datetime.now(),
            )
        ]

        reclass_file = mock_automation_env["reclass_file"]
        with open(reclass_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(r.model_dump_json() + "\n")

        # API 호출
        response = client.get("/api/automation/reclassifications")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert data["records"][0]["old_category"] == "Inbox"
        assert data["records"][0]["new_category"] == "Projects"

    def test_beat_schedule_config(self):
        """
        [Config] Celery Beat 스케줄 설정 검증
        """
        from backend.celery_app.celery import app as celery_app

        schedule = celery_app.conf.beat_schedule

        # 설정된 실제 스케줄 이름 확인
        expected_tasks = [
            "daily-reclassification",
            "weekly-reclassification",
            "daily-archiving",  # Corrected
            "weekly-report",  # Corrected
            "monthly-report",  # Corrected
            "monitor-sync-status",
            "cleanup-logs",
        ]

        for task_name in expected_tasks:
            assert task_name in schedule, f"Schedule '{task_name}' is missing"

    def test_trigger_task_stub(self):
        """
        [API] 수동 트리거 (Stub) 동작 검증
        """
        response = client.post(
            "/api/automation/tasks/trigger", params={"task_type": "reclassification"}
        )
        # 현재 미구현이므로 501 반환 (404가 아니어야 함)
        assert response.status_code == 501
        assert "not implemented" in response.json()["detail"].lower()

    def test_get_logs_empty_flow(self, mock_automation_env):
        """
        [Flow - Negative] 로그 파일이 없거나 비어있는 경우
        (파일이 없는 경우)
        """
        log_file = mock_automation_env["log_file"]
        # 로그 파일 삭제하여 빈 상태 강제
        if log_file.exists():
            log_file.unlink()

        response = client.get("/api/automation/logs")
        assert response.status_code == 200

        data = response.json()
        self._assert_log_list_schema(data)
        assert data["total"] == 0
        assert data["logs"] == []

    def test_get_log_detail_not_found_flow(self, mock_automation_env):
        """
        [Flow - Negative] 존재하지 않는 로그 ID 조회 시 404 반환
        """
        non_existent_log_id = "non-existent-log-id"

        response = client.get(f"/api/automation/logs/{non_existent_log_id}")
        assert response.status_code == 404

        # 에러 응답 구조 검증 (헬퍼 사용)
        error_data = response.json()
        self._assert_error_schema(error_data)
        # 상세 메시지 검증 (Log not found)
        assert "not found" in error_data["detail"].lower()

    def test_get_logs_empty_file_flow(self, mock_automation_env):
        """
        [Flow - Negative] 로그 파일이 존재하지만 비어있는 경우 (0바이트)
        """
        log_file = mock_automation_env["log_file"]
        # 빈 파일 생성
        log_file.write_text("", encoding="utf-8")

        response = client.get("/api/automation/logs")
        assert response.status_code == 200

        data = response.json()
        # 응답 구조(Contract) 검증 (헬퍼 사용)
        self._assert_log_list_schema(data)
        # 값 검증
        assert data["total"] == 0
        assert data["logs"] == []

    def test_get_logs_non_empty_file_flow_schema(
        self, mock_automation_env, seeded_logs
    ):
        """
        [Flow - Schema] 로그가 존재하는 경우 응답 스키마 및 내부 원소 타입 검증
        """
        # seeded_logs 픽스처가 이미 로그 파일을 생성해둠
        response = client.get("/api/automation/logs")
        assert response.status_code == 200
        data = response.json()

        # 기본 구조 검증 (헬퍼 재사용)
        self._assert_log_list_schema(data)

        # 내부 원소 검증
        assert len(data["logs"]) > 0
        for log in data["logs"]:
            assert isinstance(log, dict)
            # 필수 키 일부 검증 (API Contract)
            assert "log_id" in log
            assert "task_type" in log
            assert "status" in log
            assert "started_at" in log

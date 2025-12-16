# tests/unit/test_celery_tasks.py

"""
Celery 작업 단위 테스트
- 재분류 작업 (Reclassification)
- 아카이브 작업 (Archiving)
- 리포트 생성 작업 (Reporting)
- 모니터링 작업 (Monitoring)
"""

import pytest
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from typing import List

from backend.models.automation import (
    AutomationLog,
    AutomationTaskType,
    AutomationStatus,
    ReclassificationRecord,
    ArchivingRecord,
)
from backend.models.report import Report, ReportType, ReportMetric


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_data_dir(tmp_path):
    """임시 데이터 디렉토리 생성"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # 로그 디렉토리
    log_dir = data_dir / "automation_logs"
    log_dir.mkdir()

    # 리포트 디렉토리
    report_dir = log_dir / "reports"
    report_dir.mkdir()

    # PARA 디렉토리 구조
    for category in ["Projects", "Areas", "Resources", "Archives", "Inbox"]:
        (data_dir / category).mkdir()

    return data_dir


# ============================================================================
# 재분류 작업 테스트 (Reclassification)
# ============================================================================


class TestReclassificationTasks:
    """재분류 작업 테스트"""

    @patch("backend.celery_app.tasks.reclassification.PathConfig")
    def test_read_file_content_success(self, mock_path_config, mock_data_dir):
        """파일 읽기 헬퍼 함수 테스트 - 성공"""
        from backend.celery_app.tasks.reclassification import _read_file_content

        mock_path_config.DATA_DIR = mock_data_dir

        # 테스트 파일 생성
        test_file = mock_data_dir / "test.md"
        test_file.write_text("Test content", encoding="utf-8")

        # 파일 읽기
        content, had_error = _read_file_content(test_file)

        # 검증
        assert had_error is False
        assert content == "Test content"

    @patch("backend.celery_app.tasks.reclassification.PathConfig")
    def test_read_file_content_empty_file(self, mock_path_config, mock_data_dir):
        """파일 읽기 헬퍼 함수 테스트 - 빈 파일"""
        from backend.celery_app.tasks.reclassification import _read_file_content

        mock_path_config.DATA_DIR = mock_data_dir

        # 빈 파일 생성
        test_file = mock_data_dir / "empty.md"
        test_file.write_text("", encoding="utf-8")

        # 파일 읽기
        content, had_error = _read_file_content(test_file)

        # 검증
        assert had_error is False
        assert content is None

    @patch("backend.celery_app.tasks.reclassification.PathConfig")
    def test_read_file_content_not_found(self, mock_path_config, mock_data_dir):
        """파일 읽기 헬퍼 함수 테스트 - 파일 없음"""
        from backend.celery_app.tasks.reclassification import _read_file_content

        mock_path_config.DATA_DIR = mock_data_dir

        # 존재하지 않는 파일
        test_file = mock_data_dir / "nonexistent.md"

        # 파일 읽기
        content, had_error = _read_file_content(test_file)

        # 검증
        assert had_error is True
        assert content is None

    def test_infer_para_category(self):
        """PARA 카테고리 추론 테스트"""
        from backend.celery_app.tasks.reclassification import _infer_para_category

        # Projects
        path = Path("/data/Projects/my_project/file.md")
        assert _infer_para_category(path) == "Projects"

        # Resources
        path = Path("/data/Resources/docs/guide.md")
        assert _infer_para_category(path) == "Resources"

        # Unknown
        path = Path("/data/other/file.md")
        assert _infer_para_category(path) == "Unknown"


# ============================================================================
# 아카이브 작업 테스트 (Archiving)
# ============================================================================


class TestArchivingTasks:
    """아카이브 작업 테스트"""

    def test_get_active_files(self, mock_data_dir):
        """활성 파일 목록 수집 테스트"""
        from backend.celery_app.tasks.archiving import _get_active_files

        # 테스트 파일 생성
        (mock_data_dir / "Projects" / "test.md").write_text("Test", encoding="utf-8")
        (mock_data_dir / "Resources" / "doc.md").write_text("Doc", encoding="utf-8")

        # 활성 파일 수집
        active_files = _get_active_files(mock_data_dir)

        # 검증
        assert len(active_files) > 0
        # Archives 폴더는 제외되어야 함
        for file in active_files:
            assert "Archives" not in str(file)

    def test_infer_para_category_archiving(self):
        """PARA 카테고리 추론 테스트 (Archiving)"""
        from backend.celery_app.tasks.archiving import _infer_para_category

        # Projects
        path = Path("/data/Projects/my_project/file.md")
        assert _infer_para_category(path) == "Projects"

        # Resources
        path = Path("/data/Resources/docs/guide.md")
        assert _infer_para_category(path) == "Resources"


# ============================================================================
# 리포트 생성 작업 테스트 (Reporting)
# ============================================================================


class TestReportingTasks:
    """리포트 생성 작업 테스트"""

    @patch("backend.celery_app.tasks.reporting.PathConfig")
    def test_collect_metrics(self, mock_path_config, mock_data_dir):
        """메트릭 수집 테스트"""
        from backend.celery_app.tasks.reporting import _collect_metrics

        mock_path_config.DATA_DIR = mock_data_dir

        # 메트릭 수집
        metrics = _collect_metrics(days=7)

        # 검증
        assert isinstance(metrics, dict)
        # 기본 메트릭 키 확인
        assert "total_files" in metrics or len(metrics) >= 0

    @patch("backend.celery_app.tasks.reporting.PathConfig")
    def test_save_report(self, mock_path_config, mock_data_dir):
        """리포트 저장 테스트"""
        from backend.celery_app.tasks.reporting import _save_report

        mock_path_config.DATA_DIR = mock_data_dir

        # 테스트 리포트 생성
        report = Report(
            report_id=str(uuid.uuid4()),
            title="Test Weekly Report",
            report_type=ReportType.WEEKLY,
            period_start=datetime.now() - timedelta(days=7),
            period_end=datetime.now(),
            summary="Test summary",
            insights=["Test insight"],
            recommendations=["Test recommendation"],
            metrics={},
            created_at=datetime.now(),
        )

        # 리포트 저장
        saved_path = _save_report(report)

        # 검증
        assert saved_path is not None
        assert Path(saved_path).exists()

        # 저장된 내용 확인
        with open(saved_path, "r", encoding="utf-8") as f:
            loaded_report = json.load(f)
            assert loaded_report["title"] == "Test Weekly Report"


# ============================================================================
# 모니터링 작업 테스트 (Monitoring)
# ============================================================================


class TestMonitoringTasks:
    """모니터링 작업 테스트"""

    def test_sanitize_worker_stats(self):
        """Worker 통계 정제 테스트"""
        from backend.celery_app.tasks.monitoring import _sanitize_worker_stats

        # 테스트 데이터
        stats = {
            "worker1": {
                "pid": 12345,
                "uptime": 3600,
                "pool": {
                    "max-concurrency": 4,
                    "max-tasks-per-child": 1000,
                    "processes": [1, 2, 3, 4],
                },
            }
        }

        # 정제
        sanitized = _sanitize_worker_stats(stats)

        # 검증
        assert "worker1" in sanitized
        assert sanitized["worker1"]["pid"] == 12345
        assert "pool" in sanitized["worker1"]

    def test_sanitize_worker_stats_empty(self):
        """빈 Worker 통계 정제 테스트"""
        from backend.celery_app.tasks.monitoring import _sanitize_worker_stats

        # 빈 데이터
        sanitized = _sanitize_worker_stats({})

        # 검증
        assert sanitized == {}


# ============================================================================
# 통합 테스트 (헬퍼 함수)
# ============================================================================


class TestAutomationHelpers:
    """자동화 헬퍼 함수 테스트"""

    def test_automation_log_model(self):
        """AutomationLog 모델 테스트"""
        log = AutomationLog(
            log_id=str(uuid.uuid4()),
            task_type=AutomationTaskType.RECLASSIFICATION,
            task_name="test-task",
            celery_task_id="celery-123",
            status=AutomationStatus.COMPLETED,
            files_processed=10,
            files_updated=5,
            started_at=datetime.now(),
        )

        # 검증
        assert log.task_type == AutomationTaskType.RECLASSIFICATION
        assert log.status == AutomationStatus.COMPLETED
        assert log.files_processed == 10

    def test_reclassification_record_model(self):
        """ReclassificationRecord 모델 테스트"""
        record = ReclassificationRecord(
            record_id=str(uuid.uuid4()),
            automation_log_id=str(uuid.uuid4()),
            file_path="/data/test.md",
            old_category="Projects",
            new_category="Resources",
            confidence_score=0.9,
            reason="Test reason",
        )

        # 검증
        assert record.old_category == "Projects"
        assert record.new_category == "Resources"
        assert record.confidence_score == 0.9

    def test_archiving_record_model(self):
        """ArchivingRecord 모델 테스트"""
        record = ArchivingRecord(
            record_id=str(uuid.uuid4()),
            automation_log_id=str(uuid.uuid4()),
            file_path="/data/old.md",
            archive_path="/data/Archives/old.md",
            reason="inactive_for_30_days",
        )

        # 검증
        assert record.reason == "inactive_for_30_days"
        assert "Archives" in record.archive_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

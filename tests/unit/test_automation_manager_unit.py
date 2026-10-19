# tests/unit/test_automation_manager_unit.py

"""
Unit tests for AutomationManager defensive coding enhancements (#12.3.29).
Covers:
- _read_jsonl_logs(): Null/type safety, non-dict validation, log spam prevention (summary warning), OSError handling
- _load_all_rules() / _persist_all_rules(): malformed rule recovery, summary warning, atomic file write & cleanup
- Rule CRUD: Null/empty rule_id checks, duplicate prevention, non-existent rule handling
- Log and history queries: Enum & str conversion safety, invalid record skipping with summary warning
"""

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.models.automation import (
    ArchivingRecord,
    AutomationLog,
    AutomationRule,
    AutomationStatus,
    AutomationTaskType,
    ReclassificationRecord,
)
from backend.services.automation_manager import AutomationManager


@pytest.fixture
def mock_automation_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """테스트용 격리된 파일 경로 픽스처"""
    log_dir = tmp_path / "automation_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    auto_log = log_dir / "automation.jsonl"
    reclass_log = log_dir / "reclassification.jsonl"
    archive_log = log_dir / "archiving.jsonl"
    rules_file = log_dir / "automation_rules.jsonl"

    import backend.services.automation_manager as am

    monkeypatch.setattr(am, "LOG_DIR", log_dir)
    monkeypatch.setattr(am, "AUTO_LOG_FILE", auto_log)
    monkeypatch.setattr(am, "RECLASS_LOG_FILE", reclass_log)
    monkeypatch.setattr(am, "ARCHIVE_LOG_FILE", archive_log)
    monkeypatch.setattr(am, "RULES_FILE", rules_file)

    manager = AutomationManager()

    return {
        "log_dir": log_dir,
        "auto_log": auto_log,
        "reclass_log": reclass_log,
        "archive_log": archive_log,
        "rules_file": rules_file,
        "manager": manager,
    }


# ============================================================================
# 1. _read_jsonl_logs() 방어 코드 검증
# ============================================================================


def test_read_jsonl_logs_empty_or_nonexistent(mock_automation_env):
    """존재하지 않거나 비어있는 파일 경로 처리 시 안전하게 빈 리스트 반환"""
    manager = mock_automation_env["manager"]

    # 파일이 존재하지 않는 경우
    assert manager._read_jsonl_logs(Path("non_existent_file.jsonl")) == []

    # None 또는 유효하지 않은 경로인 경우
    assert manager._read_jsonl_logs(None) == []


def test_read_jsonl_logs_skips_malformed_and_non_dict(mock_automation_env, caplog):
    """
    손상된 JSON 줄 및 비-dict 줄(문자열, 숫자, 리스트)을 안전하게 건너뛰며,
    루프 내 개별 경고 대신 1회의 요약 로그(Summary Warning)를 출력하는지 검증
    """
    manager = mock_automation_env["manager"]
    auto_log = mock_automation_env["auto_log"]

    # 정상 2건, 손상된 JSON 2건, 비-dict JSON 2건 (총 4건 실패)
    lines = [
        json.dumps(
            {"log_id": "log-1", "task_type": "archiving", "status": "completed"}
        ),
        "{ malformed json string ...",
        json.dumps("just a plain string"),
        json.dumps([1, 2, 3]),
        "{ another broken json line",
        json.dumps(
            {"log_id": "log-2", "task_type": "archiving", "status": "completed"}
        ),
    ]
    auto_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        logs = manager._read_jsonl_logs(auto_log)

    # 유효한 2건만 역순(최신순)으로 반환되어야 함
    assert len(logs) == 2
    assert logs[0]["log_id"] == "log-2"
    assert logs[1]["log_id"] == "log-1"

    # 개별 라인 경고가 아닌 집계 요약 로그 1회 출력 확인
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    summary_logs = [r for r in warning_records if "_read_jsonl_logs:" in r.getMessage()]
    assert len(summary_logs) == 1
    assert "4 malformed line(s) skipped" in summary_logs[0].getMessage()


def test_read_jsonl_logs_limit_validation(mock_automation_env):
    """limit 매개변수 유효성 검사 (Fail-Fast: boolean 금지, 음수 금지)"""
    manager = mock_automation_env["manager"]
    auto_log = mock_automation_env["auto_log"]
    auto_log.write_text(json.dumps({"log_id": "1"}) + "\n")

    with pytest.raises(TypeError, match="limit must be a non-boolean int"):
        manager._read_jsonl_logs(auto_log, limit=True)

    with pytest.raises(TypeError, match="limit must be a non-boolean int"):
        manager._read_jsonl_logs(auto_log, limit="10")

    with pytest.raises(ValueError, match="limit must be non-negative"):
        manager._read_jsonl_logs(auto_log, limit=-1)


def test_read_jsonl_logs_oserror_handled_safely(mock_automation_env):
    """파일 읽기 중 OSError 발생 시 예외를 삼키고 빈 리스트 반환 및 구조화 로깅"""
    manager = mock_automation_env["manager"]
    auto_log = mock_automation_env["auto_log"]
    auto_log.write_text("test")

    with patch("builtins.open", side_effect=OSError("Disk read failure")):
        result = manager._read_jsonl_logs(auto_log)
        assert result == []


# ============================================================================
# 2. _load_all_rules() / _persist_all_rules() 방어 코드 검증
# ============================================================================


def test_load_all_rules_skips_malformed_with_summary_log(mock_automation_env, caplog):
    """규칙 파일 로드 시 손상된 항목을 건너뛰고 요약 로그 1회 출력"""
    manager = mock_automation_env["manager"]
    rules_file = mock_automation_env["rules_file"]

    valid_rule = AutomationRule(
        rule_id="rule-valid-1",
        name="Valid Rule",
        task_type=AutomationTaskType.ARCHIVING,
    )

    lines = [
        valid_rule.model_dump_json(),
        "invalid json line",
        json.dumps({"rule_id": "incomplete"}),  # 필수 필드(name, task_type) 누락
        json.dumps("plain string"),  # 비-dict
    ]
    rules_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        rules = manager._load_all_rules()

    assert len(rules) == 1
    assert rules[0].rule_id == "rule-valid-1"

    summary_logs = [r for r in caplog.records if "_load_all_rules:" in r.getMessage()]
    assert len(summary_logs) == 1
    assert "3 malformed rule entry(ies) skipped" in summary_logs[0].getMessage()


def test_persist_all_rules_atomic_and_validation(mock_automation_env):
    """원자적 저장 실패 시 임시 파일 정리 및 비정상 인자 방어"""
    manager = mock_automation_env["manager"]
    rules_file = mock_automation_env["rules_file"]

    # None 입력 방어
    with pytest.raises(ValueError, match="rules list cannot be None"):
        manager._persist_all_rules(None)

    # 비-AutomationRule 인자 방어
    with pytest.raises(TypeError, match="Expected AutomationRule"):
        manager._persist_all_rules([{"rule_id": "fake"}])

    # 정상 저장 확인
    rule = AutomationRule(
        rule_id="r1", name="R1", task_type=AutomationTaskType.RECLASSIFICATION
    )
    manager._persist_all_rules([rule])
    assert rules_file.exists()
    assert not rules_file.with_suffix(".tmp").exists()

    # 원자적 교체 중 OSError 발생 시 .tmp 파일 정리 확인
    with patch.object(Path, "replace", side_effect=OSError("Permission denied")):
        with pytest.raises(OSError):
            manager._persist_all_rules([rule])
        assert not rules_file.with_suffix(".tmp").exists()


# ============================================================================
# 3. Automation Rule CRUD 방어 코드 검증
# ============================================================================


def test_create_automation_rule_validation(mock_automation_env):
    """규칙 생성 시 Null/타입 검증 및 중복 ID 방어"""
    manager = mock_automation_env["manager"]

    # None 및 비-AutomationRule 방어
    with pytest.raises(ValueError, match="Valid AutomationRule is required"):
        manager.create_automation_rule(None)

    with pytest.raises(ValueError, match="Valid AutomationRule is required"):
        manager.create_automation_rule({"rule_id": "r1"})

    # 정상 생성
    rule1 = AutomationRule(
        rule_id="r-unique-1",
        name="Unique Rule 1",
        task_type=AutomationTaskType.ARCHIVING,
    )
    created = manager.create_automation_rule(rule1)
    assert created.rule_id == "r-unique-1"

    # 중복 ID 생성 시 ValueError 발생
    with pytest.raises(ValueError, match="Rule already exists: r-unique-1"):
        manager.create_automation_rule(rule1)


def test_update_automation_rule_validation(mock_automation_env):
    """규칙 수정 시 입력값 검증 및 존재하지 않는 rule_id 안전 처리"""
    manager = mock_automation_env["manager"]

    # 유효하지 않은 rule_id
    rule = AutomationRule(
        rule_id="r1", name="Rule 1", task_type=AutomationTaskType.ARCHIVING
    )
    with pytest.raises(ValueError, match="rule_id must not be empty"):
        manager.update_automation_rule("", rule)

    with pytest.raises(ValueError, match="rule_id must not be empty"):
        manager.update_automation_rule("   ", rule)

    with pytest.raises(ValueError, match="Valid AutomationRule is required"):
        manager.update_automation_rule("r1", None)

    # 존재하지 않는 rule_id 수정 시 None 반환
    assert manager.update_automation_rule("non_existent", rule) is None

    # 생성 후 정상 수정
    manager.create_automation_rule(rule)
    updated_rule = AutomationRule(
        rule_id="r1_mismatched",
        name="Updated Name",
        task_type=AutomationTaskType.REPORTING,
    )
    res = manager.update_automation_rule("r1", updated_rule)
    assert res is not None
    assert res.rule_id == "r1"  # 경로 ID와 정합성 일치
    assert res.name == "Updated Name"


def test_delete_automation_rule_validation(mock_automation_env):
    """규칙 삭제 시 빈 rule_id 방어 및 삭제 결과 반환"""
    manager = mock_automation_env["manager"]

    # 빈 ID는 False 반환
    assert manager.delete_automation_rule("") is False
    assert manager.delete_automation_rule("   ") is False

    rule = AutomationRule(
        rule_id="to_delete", name="Del", task_type=AutomationTaskType.MONITORING
    )
    manager.create_automation_rule(rule)

    assert manager.delete_automation_rule("to_delete") is True
    # 이미 삭제된 후 다시 삭제 시도
    assert manager.delete_automation_rule("to_delete") is False


# ============================================================================
# 4. 조회 메서드 방어 코드 검증
# ============================================================================


def test_get_automation_logs_enum_and_string_handling(mock_automation_env):
    """task_type 및 status 필터링 시 Enum과 문자열 모두 안전하게 처리"""
    manager = mock_automation_env["manager"]
    auto_log = mock_automation_env["auto_log"]

    log1 = AutomationLog(
        log_id="l1",
        task_type=AutomationTaskType.ARCHIVING,
        task_name="t1",
        celery_task_id="c1",
        status=AutomationStatus.COMPLETED,
    )
    log2 = AutomationLog(
        log_id="l2",
        task_type=AutomationTaskType.RECLASSIFICATION,
        task_name="t2",
        celery_task_id="c2",
        status=AutomationStatus.FAILED,
    )
    auto_log.write_text(
        log1.model_dump_json() + "\n" + log2.model_dump_json() + "\n",
        encoding="utf-8",
    )

    # Enum 전달
    results = manager.get_automation_logs(
        task_type=AutomationTaskType.ARCHIVING, status=AutomationStatus.COMPLETED
    )
    assert len(results) == 1
    assert results[0].log_id == "l1"

    # 문자열 전달 (API 등에서 원시 문자열로 전달될 때 방어)
    results_str = manager.get_automation_logs(
        task_type="reclassification", status="failed"
    )
    assert len(results_str) == 1
    assert results_str[0].log_id == "l2"


def test_get_automation_log_by_id_defensive(mock_automation_env):
    """log_id가 None, 빈 문자열이거나 파일에 없을 때 안전하게 None 반환"""
    manager = mock_automation_env["manager"]

    assert manager.get_automation_log_by_id(None) is None
    assert manager.get_automation_log_by_id("") is None
    assert manager.get_automation_log_by_id("   ") is None
    assert manager.get_automation_log_by_id("missing-id") is None


def test_get_reclassification_and_archiving_history_corrupted(
    mock_automation_env, caplog
):
    """재분류 및 아카이브 이력 조회 시 손상된 데이터가 있어도 정상 데이터만 복원하고 요약 로깅"""
    manager = mock_automation_env["manager"]
    reclass_log = mock_automation_env["reclass_log"]
    archive_log = mock_automation_env["archive_log"]

    valid_reclass = ReclassificationRecord(
        record_id="rec-1",
        automation_log_id="log-1",
        file_path="vault/doc.md",
        old_category="inbox",
        new_category="project",
        confidence_score=0.95,
    )
    reclass_log.write_text(
        valid_reclass.model_dump_json() + "\n" + '{"corrupted": true}\n',
        encoding="utf-8",
    )

    valid_archive = ArchivingRecord(
        record_id="arc-1",
        automation_log_id="log-2",
        file_path="vault/old.md",
        archive_path="archive/old.md",
        reason="inactive_for_30_days",
    )
    archive_log.write_text(
        valid_archive.model_dump_json() + "\n" + '{"corrupted": true}\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        reclass_records = manager.get_reclassification_history()
        archive_records = manager.get_archiving_history()

    assert len(reclass_records) == 1
    assert reclass_records[0].record_id == "rec-1"

    assert len(archive_records) == 1
    assert archive_records[0].record_id == "arc-1"

    warning_msgs = [
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    ]
    assert any("get_reclassification_history:" in msg for msg in warning_msgs)
    assert any("get_archiving_history:" in msg for msg in warning_msgs)


def test_record_automation_log_success(mock_automation_env):
    """record_automation_log가 AUTO_LOG_FILE에 안전하게 추가 기록하는지 검증"""
    manager = mock_automation_env["manager"]
    auto_log = mock_automation_env["auto_log"]

    log = AutomationLog(
        log_id="log-trigger-1",
        task_type=AutomationTaskType.RECLASSIFICATION,
        task_name="daily-reclassify",
        celery_task_id="celery-12345",
        status=AutomationStatus.PENDING,
    )

    success = manager.record_automation_log(log)
    assert success is True
    assert auto_log.exists()

    logs = manager.get_automation_logs(limit=10)
    assert len(logs) == 1
    assert logs[0].log_id == "log-trigger-1"
    assert logs[0].celery_task_id == "celery-12345"
    assert logs[0].status == AutomationStatus.PENDING


def test_record_automation_log_none_raises(mock_automation_env):
    """record_automation_log에 None 전달 시 ValueError 발생 검증"""
    manager = mock_automation_env["manager"]
    with pytest.raises(ValueError, match="log cannot be None"):
        manager.record_automation_log(None)


def test_record_automation_log_oserror_handling(mock_automation_env, monkeypatch):
    """record_automation_log 파일 I/O 오류 시 False 반환 및 안전 로깅 검증"""
    manager = mock_automation_env["manager"]

    def mock_open(*args, **kwargs):
        raise OSError("Permission denied")

    monkeypatch.setattr("builtins.open", mock_open)

    log = AutomationLog(
        log_id="log-err-1",
        task_type=AutomationTaskType.ARCHIVING,
        task_name="archive-inactive-files",
        celery_task_id="celery-err-1",
    )

    success = manager.record_automation_log(log)
    assert success is False


def test_record_task_trigger(mock_automation_env):
    """record_task_trigger가 유효한 PENDING 로그를 생성 및 저장하는지 검증"""
    manager = mock_automation_env["manager"]

    created_log = manager.record_task_trigger(
        task_type=AutomationTaskType.REPORTING,
        task_name="generate-weekly-report",
        celery_task_id="celery-report-999",
        details={"trigger": "manual_api", "custom": "value"},
    )

    assert created_log.log_id is not None
    assert created_log.task_type == AutomationTaskType.REPORTING
    assert created_log.task_name == "generate-weekly-report"
    assert created_log.celery_task_id == "celery-report-999"
    assert created_log.status == AutomationStatus.PENDING
    assert created_log.details.get("custom") == "value"

    # get_automation_logs로 저장 여부 재확인
    fetched = manager.get_automation_logs(limit=10)
    assert len(fetched) == 1
    assert fetched[0].celery_task_id == "celery-report-999"

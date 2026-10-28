# backend/celery_app/tasks/reporting.py

import hashlib
import json
import logging
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from backend.agent.error_utils import (  # type: ignore[import]
    build_meta,
    log_agent_error,
)
from backend.celery_app.celery import app
from backend.config import PathConfig
from backend.models.automation import (
    AutomationLog,
    AutomationStatus,
    AutomationTaskType,
)
from backend.models.report import Report, ReportMetric, ReportType

logger = logging.getLogger(__name__)

# 로그 디렉토리 설정
LOG_DIR = PathConfig.DATA_DIR / "automation_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

AUTO_LOG_FILE = LOG_DIR / "automation.jsonl"
REPORT_DIR = LOG_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
_REPORTING_DB_NAME = "reporting_metrics.sqlite3"
_REPORTING_DB_TIMEOUT_SECONDS = 10
_REPORTING_IMPORT_BATCH_SIZE = 500


class _AutomationMetricLog(BaseModel):
    """Only validated, non-detail fields needed for report aggregation."""

    model_config = ConfigDict(extra="ignore")

    log_id: StrictStr = Field(min_length=1)
    task_type: AutomationTaskType
    started_at: datetime
    files_updated: StrictInt = 0
    files_archived: StrictInt = 0
    errors_count: StrictInt = 0


_METRIC_UPSERT_SQL = """
    INSERT INTO reporting_automation_metrics (
        log_hash, started_at_epoch, task_type, files_updated,
        files_archived, errors_count
    ) VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(log_hash) DO UPDATE SET
        started_at_epoch = excluded.started_at_epoch,
        task_type = excluded.task_type,
        files_updated = excluded.files_updated,
        files_archived = excluded.files_archived,
        errors_count = excluded.errors_count
"""


def _reporting_db_path() -> Path:
    """Place the reporting index under the configured application data directory."""
    return Path(PathConfig.DATA_DIR) / "db" / _REPORTING_DB_NAME


def _open_reporting_db() -> sqlite3.Connection:
    db_path = _reporting_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=_REPORTING_DB_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _initialize_reporting_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reporting_automation_metrics (
            log_hash TEXT PRIMARY KEY NOT NULL,
            started_at_epoch REAL NOT NULL,
            task_type TEXT NOT NULL,
            files_updated INTEGER NOT NULL,
            files_archived INTEGER NOT NULL,
            errors_count INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reporting_automation_metrics_period
        ON reporting_automation_metrics (started_at_epoch, task_type)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reporting_source_checkpoints (
            source_id TEXT PRIMARY KEY NOT NULL,
            source_device INTEGER NOT NULL,
            source_inode INTEGER NOT NULL,
            byte_offset INTEGER NOT NULL
        )
        """
    )
    connection.commit()


def _metric_row(line: bytes) -> Tuple[str, float, str, int, int, int]:
    """Validate one JSONL record and return its privacy-reduced DB representation."""
    decoded = line.decode("utf-8")
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("Automation log record must be a JSON object.")
    started_at_raw = payload.get("started_at")
    if not isinstance(started_at_raw, str):
        raise ValueError("Automation log record has no ISO timestamp.")

    record = _AutomationMetricLog.model_validate(payload)
    timestamp = record.started_at
    if timestamp.tzinfo is None:
        # Match the prior naive datetime comparison against local datetime.now().
        timestamp = timestamp.astimezone()
    timestamp = timestamp.astimezone(timezone.utc)
    log_hash = hashlib.sha256(record.log_id.encode("utf-8")).hexdigest()
    return (
        log_hash,
        timestamp.timestamp(),
        record.task_type.value,
        record.files_updated,
        record.files_archived,
        record.errors_count,
    )


def _import_new_automation_logs(connection: sqlite3.Connection) -> int:
    """Incrementally index complete JSONL records, using bounded memory."""
    if not AUTO_LOG_FILE.is_file():
        return 0

    malformed_count = 0
    with open(AUTO_LOG_FILE, "rb") as source:
        source_stat = os.fstat(source.fileno())
        checkpoint = connection.execute(
            """
            SELECT source_device, source_inode, byte_offset
            FROM reporting_source_checkpoints
            WHERE source_id = ?
            """,
            (AUTO_LOG_FILE.name,),
        ).fetchone()

        offset = 0
        if checkpoint is not None:
            same_file = (
                checkpoint["source_device"] == source_stat.st_dev
                and checkpoint["source_inode"] == source_stat.st_ino
            )
            if same_file and checkpoint["byte_offset"] <= source_stat.st_size:
                offset = checkpoint["byte_offset"]

        source.seek(offset)
        pending_rows: List[Tuple[str, float, str, int, int, int]] = []
        committed_offset = offset
        while True:
            line_start = source.tell()
            line = source.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                # Leave incomplete appends for the next run instead of losing them.
                source.seek(line_start)
                break

            committed_offset = source.tell()
            if not line.strip():
                continue
            try:
                pending_rows.append(_metric_row(line))
            except (
                UnicodeDecodeError,
                json.JSONDecodeError,
                ValidationError,
                ValueError,
                TypeError,
                OverflowError,
            ):
                malformed_count += 1
                continue

            if len(pending_rows) >= _REPORTING_IMPORT_BATCH_SIZE:
                connection.executemany(_METRIC_UPSERT_SQL, pending_rows)
                pending_rows.clear()

        if pending_rows:
            connection.executemany(_METRIC_UPSERT_SQL, pending_rows)

        connection.execute(
            """
            INSERT INTO reporting_source_checkpoints (
                source_id, source_device, source_inode, byte_offset
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_device = excluded.source_device,
                source_inode = excluded.source_inode,
                byte_offset = excluded.byte_offset
            """,
            (
                AUTO_LOG_FILE.name,
                source_stat.st_dev,
                source_stat.st_ino,
                committed_offset,
            ),
        )
    return malformed_count


def _save_automation_log(log: AutomationLog):
    """AutomationLog 저장"""
    try:
        with open(AUTO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log.model_dump_json() + "\n")
    except OSError as e:
        meta = build_meta({"action": "save_automation_log"})
        log_agent_error(logger, "Failed to save automation log", e, meta)


def _save_report(report: Report):
    """
    생성된 리포트를 JSON 파일로 저장
    - 실패 시 예외를 발생시켜 호출자가 처리하도록 함
    """
    # 파일명: report_{type}_{date}_{id}.json
    date_str = report.created_at.strftime("%Y%m%d")
    filename = (
        f"report_{report.report_type.value}_{date_str}_{report.report_id[:8]}.json"
    )
    path = REPORT_DIR / filename

    with open(path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    logger.info(
        "Report saved: %s", Path(path).name if isinstance(path, (str, Path)) else path
    )
    return str(path)


def _collect_metrics(days: int) -> Dict[str, ReportMetric]:
    """
    지정 기간의 자동화 지표를 SQLite 집계 쿼리로 수집한다.

    JSONL은 첫 조회 및 새로 추가된 구간만 스트리밍으로 DB에 색인하며,
    과거 전체 로그를 메모리에 적재하지 않는다.
    """
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("days must be a positive integer")

    now = datetime.now(timezone.utc)
    start_epoch = (now - timedelta(days=days)).timestamp()
    end_epoch = now.timestamp()
    try:
        with closing(_open_reporting_db()) as connection:
            _initialize_reporting_schema(connection)
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                malformed_count = _import_new_automation_logs(connection)

                retention_days = max(days, max(REPORT_PERIOD_DAYS.values()))
                retention_epoch = (now - timedelta(days=retention_days)).timestamp()
                connection.execute(
                    "DELETE FROM reporting_automation_metrics WHERE started_at_epoch < ?",
                    (retention_epoch,),
                )
                aggregate = connection.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN task_type = ? THEN files_updated ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN task_type = ? THEN files_archived ELSE 0 END), 0),
                        COALESCE(SUM(errors_count), 0)
                    FROM reporting_automation_metrics
                    WHERE started_at_epoch >= ? AND started_at_epoch <= ?
                    """,
                    (
                        AutomationTaskType.RECLASSIFICATION.value,
                        AutomationTaskType.ARCHIVING.value,
                        start_epoch,
                        end_epoch,
                    ),
                ).fetchone()

        if malformed_count:
            logger.warning(
                "Skipped malformed automation log records during SQLite indexing.",
                extra={"malformed_count": malformed_count},
            )
        reclassified, archived, errors = aggregate
        return {
            "reclassified_files": ReportMetric(
                metric_name="Reclassified Files",
                value=reclassified,
                unit="files",
                description=f"Last {days} days",
            ),
            "archived_files": ReportMetric(
                metric_name="Archived Files",
                value=archived,
                unit="files",
                description=f"Last {days} days",
            ),
            "automation_errors": ReportMetric(
                metric_name="Automation Errors",
                value=errors,
                unit="count",
                description="Total errors in period",
            ),
        }
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        meta = build_meta(
            {"action": "collect_metrics", "error_type": type(exc).__name__}
        )
        log_agent_error(
            logger,
            "Error collecting reporting metrics from SQLite",
            exc,
            meta,
            include_traceback=True,
        )
        raise


def _generate_insights(metrics: Dict[str, ReportMetric]) -> List[str]:
    """메트릭 기반 간단한 인사이트 생성"""
    insights = []

    reclassified = metrics.get(
        "reclassified_files", ReportMetric(metric_name="", value=0)
    ).value
    archived = metrics.get(
        "archived_files", ReportMetric(metric_name="", value=0)
    ).value
    errors = metrics.get(
        "automation_errors", ReportMetric(metric_name="", value=0)
    ).value

    if reclassified > 0:
        insights.append(
            f"총 {reclassified}개의 파일이 자동으로 재분류되어 정리 시간을 절약했습니다."
        )

    if archived > 0:
        insights.append(
            f"{archived}개의 사용하지 않는 파일이 아카이브로 이동되어 워크스페이스가 정리되었습니다."
        )

    if errors > 0:
        insights.append(
            f"자동화 작업 중 {errors}건의 오류가 발생했습니다. 로그 확인이 필요합니다."
        )

    if not insights:
        insights.append("특이 사항이 없는 평온한 기간이었습니다.")

    return insights


# 리포트 타입별 기간(일) 매핑
REPORT_PERIOD_DAYS = {
    ReportType.WEEKLY: 7,
    ReportType.MONTHLY: 30,
}


def _get_report_days(report_type: ReportType) -> int:
    """리포트 타입에 따른 기간(일) 반환"""
    days = REPORT_PERIOD_DAYS.get(report_type)
    if days is None:
        raise ValueError(f"Unsupported report_type: {report_type}")
    return days


def _format_report_title(
    report_type: ReportType, start: datetime, end: datetime
) -> str:
    """리포트 제목 생성 헬퍼"""
    date_fmt = "%Y-%m-%d"
    return f"{report_type.value.title()} Automation Report ({start.strftime(date_fmt)} ~ {end.strftime(date_fmt)})"


def _execute_report_task(
    celery_task_id: str,
    task_name: str,
    report_type: ReportType,
):
    # sourcery skip: extract-method
    """
    리포트 생성 공통 로직 실행
    - 로그 기록, 메트릭 수집, 리포트 생성 및 저장, 에러 처리
    """
    start_time = datetime.now()
    log_id = str(uuid.uuid4())

    log = AutomationLog(
        log_id=log_id,
        task_type=AutomationTaskType.REPORTING,
        task_name=task_name,
        celery_task_id=celery_task_id,
        status=AutomationStatus.RUNNING,
        started_at=start_time,
    )

    try:
        # 1. 메트릭 수집
        days = _get_report_days(report_type)

        period_start = start_time - timedelta(days=days)

        metrics = _collect_metrics(days=days)
        insights = _generate_insights(metrics)

        # 2. 리포트 객체 생성
        title = _format_report_title(report_type, period_start, start_time)

        report = Report(
            report_id=str(uuid.uuid4()),
            title=title,
            report_type=report_type,
            period_start=period_start,
            period_end=start_time,
            summary=f"{report_type.value.title()} report for {days} days activity.",
            insights=insights,
            recommendations=[],
            metrics=metrics,
        )

        # 3. 리포트 저장
        saved_path = _save_report(report)

        # 4. 결과 기록
        log.status = AutomationStatus.COMPLETED
        log.completed_at = datetime.now()
        log.duration_seconds = (log.completed_at - start_time).total_seconds()
        log.details = {"report_path": saved_path, "report_id": report.report_id}

        _save_automation_log(log)

        return f"{report_type.value.title()} Report generated: {report.report_id}"

    except (ValueError, TypeError, OSError, RuntimeError, sqlite3.Error) as exc:
        # 방어적 코딩 및 보안 로깅
        # 민감 정보 유출 방지를 위해 구체적인 에러 메시지 대신 에러 타입만 기록
        error_type = type(exc).__name__

        meta = build_meta(
            {
                "action": "execute_report_task",
                "task_name": task_name,
                "log_id": log_id,
                "error_type": error_type,
                "unhandled": True,
            }
        )
        log_agent_error(logger, f"{task_name} failed", exc, meta)

        log.status = AutomationStatus.FAILED
        log.details = {"error_type": error_type}  # 민감한 str(exc) 대신 타입 기록
        log.completed_at = datetime.now()
        log.duration_seconds = (log.completed_at - start_time).total_seconds()
        log.errors_count = (log.errors_count or 0) + 1

        _save_automation_log(log)
        raise  # 기존 트레이스백 보존


@app.task(bind=True)
def generate_weekly_report(self):
    """
    [주간 리포트 생성]
    - 매주 월요일 실행
    - 지난 7일간의 통계 집계
    """
    return _execute_report_task(
        celery_task_id=self.request.id,
        task_name="generate-weekly-report",
        report_type=ReportType.WEEKLY,
    )


@app.task(bind=True)
def generate_monthly_report(self):
    """
    [월간 리포트 생성]
    - 매월 1일 실행
    - 지난 30일간의 통계 집계
    """
    return _execute_report_task(
        celery_task_id=self.request.id,
        task_name="generate-monthly-report",
        report_type=ReportType.MONTHLY,
    )

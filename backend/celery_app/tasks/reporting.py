# backend/celery_app/tasks/reporting.py

import json
import uuid
import logging
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pathlib import Path

from backend.celery_app.celery import app
from backend.models.automation import (
    AutomationLog,
    AutomationTaskType,
    AutomationStatus,
    ReclassificationRecord,
    ArchivingRecord,
)
from backend.models.report import (
    Report,
    ReportType,
    ReportMetric,
)
from backend.config import PathConfig
from backend.services.file_access_logger import FileAccessLogger

logger = logging.getLogger(__name__)

# 로그 디렉토리 설정
LOG_DIR = PathConfig.DATA_DIR / "automation_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

AUTO_LOG_FILE = LOG_DIR / "automation.jsonl"
REPORT_DIR = LOG_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def _save_automation_log(log: AutomationLog):
    """AutomationLog 저장"""
    try:
        with open(AUTO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log.model_dump_json() + "\n")
    except Exception as e:
        logger.error(f"Failed to save automation log: {e}")


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

    logger.info(f"Report saved: {path}")
    return str(path)


def _collect_metrics(days: int) -> Dict[str, ReportMetric]:
    """
    지정된 기간(일) 동안의 메트릭 수집
    - 파일 접근 통계
    - 자동화 작업(재분류, 아카이브) 통계
    """
    metrics = {}
    total_processed = 0
    total_errors = 0

    # 1. 자동화 로그 분석 (AutomationLog)
    # 실제로는 DB나 JSONL을 쿼리해야 함. 여기서는 파일 직접 읽기 방식(간이 구현)
    # TODO: 추후 DB 쿼리로 개선 권장
    try:
        start_date = datetime.now() - timedelta(days=days)
        reclassify_count = 0
        archive_count = 0

        if AUTO_LOG_FILE.exists():
            malformed_log_lines = 0

            with open(AUTO_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    safe_line = line.strip()[:200]

                    # 1. JSON 파싱
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        malformed_log_lines += 1
                        continue

                    # 2. 데이터 구조 검증
                    if not isinstance(data, dict):
                        malformed_log_lines += 1
                        continue

                    started_at_str = data.get("started_at")
                    if not started_at_str:
                        malformed_log_lines += 1
                        continue

                    # 3. 날짜 파싱 및 로직 처리
                    try:
                        log_time = datetime.fromisoformat(started_at_str)

                        if log_time >= start_date:
                            task_type = data.get("task_type")

                            if task_type == AutomationTaskType.RECLASSIFICATION.value:
                                reclassify_count += data.get("files_updated", 0)
                            elif task_type == AutomationTaskType.ARCHIVING.value:
                                archive_count += data.get("files_archived", 0)

                            total_processed += data.get("files_processed", 0)
                            total_errors += data.get("errors_count", 0)

                    except (ValueError, TypeError):
                        # 날짜 포맷 에러 또는 타입 에러
                        malformed_log_lines += 1
                        continue
                    except Exception as e:
                        # 기타 예상치 못한 에러는 스택 트레이스 포함하여 로깅
                        # 방어적 코딩: safe_line이 None이거나 문자열이 아닐 경우 대비
                        safe_content = str(safe_line) if safe_line is not None else ""

                        # 민감 정보 마스킹을 위한 해시 생성
                        content_sha256 = hashlib.sha256(
                            safe_content.encode("utf-8", "ignore")
                        ).hexdigest()

                        # 디버깅을 위한 비민감 메타데이터 수집
                        meta_info = {
                            "content_sha256": content_sha256,
                            "content_length": len(safe_content),
                            "is_empty": not bool(safe_content),
                        }

                        logger.exception(
                            "Unexpected error processing log line",
                            extra=meta_info,
                        )
                        continue

            # 루프 종료 후 요약 로그
            if malformed_log_lines > 0:
                logger.warning(
                    "Skipped %d malformed log line(s) while parsing %s",
                    malformed_log_lines,
                    AUTO_LOG_FILE,
                )

        metrics["reclassified_files"] = ReportMetric(
            metric_name="Reclassified Files",
            value=reclassify_count,
            unit="files",
            description=f"Last {days} days",
        )

        metrics["archived_files"] = ReportMetric(
            metric_name="Archived Files",
            value=archive_count,
            unit="files",
            description=f"Last {days} days",
        )

        metrics["automation_errors"] = ReportMetric(
            metric_name="Automation Errors",
            value=total_errors,
            unit="count",
            description="Total errors in period",
        )

    except Exception as e:
        logger.error(f"Error collecting metrics: {e}")

    return metrics


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


def _execute_report_task(
    celery_task_id: str,
    task_name: str,
    report_type: ReportType,
    days: int,
):
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
        period_start = start_time - timedelta(days=days)
        metrics = _collect_metrics(days=days)
        insights = _generate_insights(metrics)

        # 2. 리포트 객체 생성
        date_fmt = "%Y-%m-%d"
        title = f"{report_type.value.title()} Automation Report ({period_start.strftime(date_fmt)} ~ {start_time.strftime(date_fmt)})"

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

    except Exception as e:
        # 방어적 코딩 및 보안 로깅
        logger.exception(
            f"{task_name} failed",
            extra={
                "task_name": task_name,
                "log_id": log_id,
                "error_message": str(e),
            },
        )

        log.status = AutomationStatus.FAILED
        log.details = {"error": str(e)}
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
        days=7,
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
        days=30,
    )

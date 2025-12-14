# backend/celery_app/tasks/monitoring.py

import asyncio
import logging
import uuid
import json
from datetime import datetime
from datetime import datetime
from typing import Dict, Any, TypeVar, Awaitable

from backend.celery_app.celery import app
from backend.config import PathConfig
from backend.config.mcp_config import mcp_config
from backend.mcp.obsidian_server import ObsidianSyncService
from backend.models.automation import (
    AutomationLog,
    AutomationTaskType,
    AutomationStatus,
)

logger = logging.getLogger(__name__)

# 로그 디렉토리 및 파일 설정 (Reporting과 동일 구조 사용)
LOG_DIR = PathConfig.DATA_DIR / "automation_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
AUTO_LOG_FILE = LOG_DIR / "automation.jsonl"


def _save_monitoring_log(log: AutomationLog):
    """AutomationLog 저장 (Monitoring 전용)"""
    try:
        with open(AUTO_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log.model_dump_json() + "\n")
    except Exception as exc:
        logger.error(
            "Failed to save monitoring log",
            exc_info=False,
            extra={"error_type": type(exc).__name__},
        )


def _sanitize_worker_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker 통계 데이터 정제 (로그 용량 최적화 및 직렬화 안전)
    - PID, Uptime, Pool 정보 등 핵심 지표만 추출
    """
    if not stats:
        return {}

    sanitized = {}
    for node, info in stats.items():
        if not isinstance(info, dict):
            sanitized[node] = str(info)
            continue

        sanitized[node] = {
            "pid": info.get("pid"),
            "uptime": info.get("uptime"),
            "pool": info.get("pool", {}),
            # "rusage": info.get("rusage", {}), # 너무 상세하면 제외
        }
    return sanitized


T = TypeVar("T")


def _run_coroutine_safely(coro: Awaitable[T]) -> T:
    """Executes a coroutine in a temporary event loop with safe cleanup."""
    old_loop = None
    try:
        old_loop = asyncio.get_event_loop()
    except RuntimeError:
        pass

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except Exception as exc:
            logger.warning(
                "Failed to close temporary event loop",
                exc_info=False,
                extra={
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )

        # 기존 루프가 있었을 때만 복원
        if old_loop is not None:
            asyncio.set_event_loop(old_loop)


def _run_async_check(service: ObsidianSyncService) -> bool:
    """Run async connection check synchronously with safe loop handling."""
    return _run_coroutine_safely(service.connect())


@app.task(bind=True)
def check_sync_status(self):
    """
    [동기화 상태 모니터링]
    - 매 10분마다 실행 (스케줄러 설정 필요)
    - 외부 도구(Obsidian) 연결 상태 확인
    - 에러 발생 시 로그 생성
    """
    task_name = "check_sync_status"
    start_time = datetime.now()
    log_id = str(uuid.uuid4())

    # 설정 확인
    if not mcp_config.obsidian.enabled:
        return "Obsidian Sync Disabled"

    service = ObsidianSyncService(mcp_config.obsidian)
    is_connected = False

    try:
        is_connected = _run_async_check(service)

        if not is_connected:
            end_time = datetime.now()
            # 연결 실패 시에만 AutomationLog에 ERROR로 기록
            log = AutomationLog(
                log_id=log_id,
                task_type=AutomationTaskType.MONITORING,
                task_name=task_name,
                celery_task_id=self.request.id,
                status=AutomationStatus.FAILED,
                started_at=start_time,
                completed_at=end_time,
                duration_seconds=(end_time - start_time).total_seconds(),
                details={
                    "error": "Obsidian Connection Failed",
                    "vault_path": mcp_config.obsidian.vault_path,
                },
                errors_count=1,
            )
            _save_monitoring_log(log)

            logger.error(
                "❌ External Tool Connection Failed",
                exc_info=False,
                extra={
                    "tool": "Obsidian",
                    "vault_path": mcp_config.obsidian.vault_path,
                    "task_name": task_name,
                    "error_type": "ConnectionError",
                },
            )
            return "Connection Failed"

        # 성공 시에는 로그를 남기지 않거나, INFO 레벨만 기록 (Log flooding 방지)
        logger.info(f"✅ Sync Status Check Passed: {mcp_config.obsidian.vault_path}")
        return "Healthy"

    except Exception as exc:
        error_type = type(exc).__name__
        logger.error(
            f"{task_name} unexpected error",
            exc_info=False,
            extra={"task_name": task_name, "error_type": error_type, "unhandled": True},
        )

        end_time = datetime.now()
        # 예기치 못한 에러도 로그에 남김
        log = AutomationLog(
            log_id=log_id,
            task_type=AutomationTaskType.MONITORING,
            task_name=task_name,
            celery_task_id=self.request.id,
            status=AutomationStatus.FAILED,
            started_at=start_time,
            completed_at=end_time,
            duration_seconds=(end_time - start_time).total_seconds(),
            details={"error_type": error_type},
            errors_count=1,
        )
        _save_monitoring_log(log)

        raise


@app.task(bind=True)
def check_task_health(self):
    """
    [Celery Worker & Task 상태 모니터링]
    - Worker 생존 확인 (ping)
    - Worker 통계 수집 (stats)
    """
    task_name = "check_task_health"
    start_time = datetime.now()
    log_id = str(uuid.uuid4())

    details = {}
    is_healthy = True
    error_msg = None

    try:
        # 1. Worker Ping Check
        # app.control.ping() returns list of dicts: [{'celery@hostname': {'ok': 'pong'}}, ...]
        ping_result = app.control.ping(timeout=3.0)
        active_workers = []

        if ping_result:
            for node in ping_result:
                active_workers.extend(node.keys())

        details["active_workers"] = active_workers

        if not active_workers:
            is_healthy = False
            error_msg = "No active Celery workers found"

        # 2. Worker Stats (Optional performance metrics)
        if is_healthy:
            # inspect().stats() may return None if no workers respond
            inspector = app.control.inspect()
            stats = inspector.stats()
            if stats:
                details["worker_stats"] = _sanitize_worker_stats(stats)
            else:
                details["worker_stats"] = "No stats available"

        # 3. Log Result
        status = AutomationStatus.COMPLETED if is_healthy else AutomationStatus.FAILED

        if not is_healthy:
            end_time = datetime.now()
            # 실패 시에만 AutomationLog 저장
            log = AutomationLog(
                log_id=log_id,
                task_type=AutomationTaskType.MONITORING,
                task_name=task_name,
                celery_task_id=self.request.id,
                status=status,
                started_at=start_time,
                completed_at=end_time,
                duration_seconds=(end_time - start_time).total_seconds(),
                details=details,
                errors_count=1 if not is_healthy else 0,
            )
            # Add error detail if exists
            if error_msg:
                log.details["error"] = error_msg

            _save_monitoring_log(log)

            logger.error(
                f"❌ {task_name} Failed: {error_msg}",
                exc_info=False,
                extra={
                    "task_name": task_name,
                    "active_workers": active_workers,
                    "error_type": "WorkerHealthError",
                },
            )
            return f"Health Check Failed: {error_msg}"

        return f"Healthy. Active Workers: {len(active_workers)}"

    except Exception as exc:
        error_type = type(exc).__name__
        logger.error(
            f"{task_name} unexpected error",
            exc_info=False,
            extra={"task_name": task_name, "error_type": error_type, "unhandled": True},
        )

        end_time = datetime.now()
        # 예기치 못한 에러도 로그에 남김
        log = AutomationLog(
            log_id=log_id,
            task_type=AutomationTaskType.MONITORING,
            task_name=task_name,
            celery_task_id=self.request.id,
            status=AutomationStatus.FAILED,
            started_at=start_time,
            completed_at=end_time,
            duration_seconds=(end_time - start_time).total_seconds(),
            details={"error_type": error_type},
            errors_count=1,
        )
        _save_monitoring_log(log)
        raise

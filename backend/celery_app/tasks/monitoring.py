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

        # Pool 정보에서 원시 타입 필드만 추출
        pool_info = info.get("pool", {})
        sanitized_pool = {}
        if isinstance(pool_info, dict):
            # 직렬화 가능한 원시 타입 필드만 화이트리스트
            for key in [
                "max-concurrency",
                "max-tasks-per-child",
                "processes",
                "timeouts",
            ]:
                if key in pool_info:
                    val = pool_info[key]
                    # 원시 타입만 허용
                    if isinstance(val, (int, float, str, bool, type(None))):
                        sanitized_pool[key] = val

        sanitized[node] = {
            "pid": info.get("pid"),
            "uptime": info.get("uptime"),
            "pool": sanitized_pool,
        }
    return sanitized


def _create_failed_log(
    log_id: str,
    task_name: str,
    celery_task_id: str,
    start_time: datetime,
    details: Dict[str, Any],
    errors_count: int = 1,
) -> AutomationLog:
    """
    실패한 모니터링 태스크의 AutomationLog 생성 (시간 일관성 보장)
    """
    end_time = datetime.now()
    return AutomationLog(
        log_id=log_id,
        task_type=AutomationTaskType.MONITORING,
        task_name=task_name,
        celery_task_id=celery_task_id,
        status=AutomationStatus.FAILED,
        started_at=start_time,
        completed_at=end_time,
        duration_seconds=(end_time - start_time).total_seconds(),
        details=details,
        errors_count=errors_count,
    )


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
            # 연결 실패 시에만 AutomationLog에 ERROR로 기록
            log = _create_failed_log(
                log_id=log_id,
                task_name=task_name,
                celery_task_id=self.request.id,
                start_time=start_time,
                details={
                    "error": "Obsidian Connection Failed",
                    "vault_path": mcp_config.obsidian.vault_path,
                },
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

        # 예기치 못한 에러도 로그에 남김
        log = _create_failed_log(
            log_id=log_id,
            task_name=task_name,
            celery_task_id=self.request.id,
            start_time=start_time,
            details={"error_type": error_type},
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
            # 실패 시에만 AutomationLog 저장
            log = _create_failed_log(
                log_id=log_id,
                task_name=task_name,
                celery_task_id=self.request.id,
                start_time=start_time,
                details=details,
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

        # 예기치 못한 에러도 로그에 남김
        log = _create_failed_log(
            log_id=log_id,
            task_name=task_name,
            celery_task_id=self.request.id,
            start_time=start_time,
            details={"error_type": error_type},
        )
        _save_monitoring_log(log)
        raise

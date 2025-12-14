# backend/celery_app/tasks/monitoring.py

import asyncio
import logging
import uuid
import json
from datetime import datetime
from typing import Dict, Any

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


def _run_coroutine_safely(coro: Any) -> Any:
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
            log = AutomationLog(
                log_id=log_id,
                task_type=AutomationTaskType.MONITORING,
                task_name=task_name,
                celery_task_id=self.request.id,
                status=AutomationStatus.FAILED,
                started_at=start_time,
                completed_at=datetime.now(),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
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
        # 예기치 못한 에러도 로그에 남김
        log = AutomationLog(
            log_id=log_id,
            task_type=AutomationTaskType.MONITORING,
            task_name=task_name,
            celery_task_id=self.request.id,
            status=AutomationStatus.FAILED,
            started_at=start_time,
            completed_at=datetime.now(),
            duration_seconds=(datetime.now() - start_time).total_seconds(),
            details={"error_type": error_type},
            errors_count=1,
        )
        _save_monitoring_log(log)

        raise

# backend/api/endpoints/automation.py

"""
Automation API Endpoints
자동화 작업 로그, 규칙, 이력 조회 및 관리 API
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from fastapi import Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError

from backend.agent.error_utils import build_meta, log_agent_error
from backend.celery_app.tasks.archiving import (
    archive_inactive_files,
    auto_archive_tasks,
)
from backend.celery_app.tasks.maintenance import (
    backup_automation_data,
    cleanup_old_logs,
)
from backend.celery_app.tasks.monitoring import check_sync_status, check_task_health
from backend.celery_app.tasks.reclassification import (
    daily_reclassify_tasks,
    weekly_reclassify_tasks,
)
from backend.celery_app.tasks.reporting import (
    generate_monthly_report,
    generate_weekly_report,
)
from backend.config import PathConfig
from backend.mcp.sync_map_manager import get_sync_map_manager
from backend.models.automation import (
    ArchivingRecord,
    AutomationLog,
    AutomationRule,
    AutomationStatus,
    AutomationTaskType,
    ReclassificationRecord,
)
from backend.services.automation_manager import automation_manager

router = APIRouter(prefix="/automation", tags=["automation"])
logger = logging.getLogger(__name__)


# ============================================================================
# Response Models
# ============================================================================


class AutomationLogListResponse(BaseModel):
    """자동화 로그 목록 응답"""

    total: int = Field(..., description="전체 로그 수")
    logs: List[AutomationLog] = Field(..., description="로그 목록")


class AutomationRuleListResponse(BaseModel):
    """자동화 규칙 목록 응답"""

    total: int = Field(..., description="전체 규칙 수")
    rules: List[AutomationRule] = Field(..., description="규칙 목록")


class ReclassificationHistoryResponse(BaseModel):
    """재분류 이력 응답"""

    total: int = Field(..., description="전체 재분류 수")
    records: List[ReclassificationRecord] = Field(..., description="재분류 기록")


class ArchivingHistoryResponse(BaseModel):
    """아카이브 이력 응답"""

    total: int = Field(..., description="전체 아카이브 수")
    records: List[ArchivingRecord] = Field(..., description="아카이브 기록")


class TaskTriggerResponse(BaseModel):
    """수동 태스크 트리거 응답"""

    task_id: str = Field(..., description="Celery 비동기 작업 ID")
    task_type: AutomationTaskType = Field(..., description="트리거된 작업 유형")
    task_name: str = Field(..., description="트리거된 세부 작업명")
    status: str = Field("queued", description="태스크 상태")
    message: str = Field(..., description="안내 메시지")
    triggered_at: datetime = Field(..., description="트리거 요청 시각 (UTC)")


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/logs", response_model=AutomationLogListResponse)
def get_automation_logs(
    limit: int = Query(100, ge=1, le=1000, description="최대 반환 개수"),
    task_type: Optional[AutomationTaskType] = Query(None, description="작업 유형 필터"),
    status: Optional[AutomationStatus] = Query(None, description="상태 필터"),
):
    """
    자동화 로그 목록 조회

    - 최근 실행된 자동화 작업 로그 조회
    - task_type, status로 필터링 가능
    """
    logs = automation_manager.get_automation_logs(
        limit=limit, task_type=task_type, status=status
    )

    return AutomationLogListResponse(total=len(logs), logs=logs)


@router.get("/logs/{log_id}", response_model=AutomationLog)
def get_automation_log_detail(log_id: str = PathParam(..., description="로그 ID")):
    """
    자동화 로그 상세 조회

    - 특정 로그의 상세 정보 조회
    """
    log = automation_manager.get_automation_log_by_id(log_id)

    if log is None:
        raise HTTPException(status_code=404, detail=f"Log not found: {log_id}")

    return log


@router.get("/rules", response_model=AutomationRuleListResponse)
def get_automation_rules():
    """
    자동화 규칙 목록 조회

    - JSONL 기반 임시 저장소에서 조회
    - 향후 DB 연동 시 교체 예정
    """
    rules = automation_manager.get_automation_rules()
    return AutomationRuleListResponse(total=len(rules), rules=rules)


@router.post("/rules", response_model=AutomationRule, status_code=201)
def create_automation_rule(rule: AutomationRule):
    """
    자동화 규칙 생성

    - 새로운 자동화 규칙 생성 (JSONL 저장소에 추가)
    """
    try:
        return automation_manager.create_automation_rule(rule)
    except ValueError as exc:
        raise HTTPException(
            status_code=409, detail="Rule with this ID already exists."
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="Failed to save automation rule."
        ) from exc


@router.put("/rules/{rule_id}", response_model=AutomationRule)
def update_automation_rule(
    rule: AutomationRule, rule_id: str = PathParam(..., description="규칙 ID")
):
    """
    자동화 규칙 수정

    - 기존 규칙 수정 (JSONL 저장소 갱신)
    """
    try:
        result = automation_manager.update_automation_rule(rule_id, rule)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
        return result
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="Failed to update automation rule."
        ) from exc


@router.delete("/rules/{rule_id}", status_code=204)
def delete_automation_rule(rule_id: str = PathParam(..., description="규칙 ID")):
    """
    자동화 규칙 삭제

    - 기존 규칙 삭제 (JSONL 저장소 갱신)
    """
    try:
        success = automation_manager.delete_automation_rule(rule_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail="Failed to delete automation rule."
        ) from exc


@router.get("/reclassifications", response_model=ReclassificationHistoryResponse)
def get_reclassification_history(
    limit: int = Query(100, ge=1, le=1000, description="최대 반환 개수")
):
    """
    재분류 이력 조회

    - 최근 재분류 작업 이력 조회
    """
    records = automation_manager.get_reclassification_history(limit=limit)
    return ReclassificationHistoryResponse(total=len(records), records=records)


@router.get("/archives", response_model=ArchivingHistoryResponse)
def get_archiving_history(
    limit: int = Query(100, ge=1, le=1000, description="최대 반환 개수")
):
    """
    아카이브 이력 조회

    - 최근 아카이브 작업 이력 조회
    """
    records = automation_manager.get_archiving_history(limit=limit)
    return ArchivingHistoryResponse(total=len(records), records=records)


# ============================================================================
# Celery Manual Task Registry
# ============================================================================

TASK_REGISTRY = {
    AutomationTaskType.RECLASSIFICATION: {
        "default": (daily_reclassify_tasks, "daily-reclassify"),
        "daily-reclassify": (daily_reclassify_tasks, "daily-reclassify"),
        "daily": (daily_reclassify_tasks, "daily-reclassify"),
        "weekly-reclassify": (weekly_reclassify_tasks, "weekly-reclassify"),
        "weekly": (weekly_reclassify_tasks, "weekly-reclassify"),
    },
    AutomationTaskType.ARCHIVING: {
        "default": (archive_inactive_files, "archive-inactive-files"),
        "archive-inactive-files": (archive_inactive_files, "archive-inactive-files"),
        "auto_archive": (auto_archive_tasks, "auto_archive_tasks"),
        "auto-archive": (auto_archive_tasks, "auto_archive_tasks"),
        "archive": (archive_inactive_files, "archive-inactive-files"),
    },
    AutomationTaskType.REPORTING: {
        "default": (generate_weekly_report, "generate-weekly-report"),
        "generate-weekly-report": (generate_weekly_report, "generate-weekly-report"),
        "weekly": (generate_weekly_report, "generate-weekly-report"),
        "generate-monthly-report": (generate_monthly_report, "generate-monthly-report"),
        "monthly": (generate_monthly_report, "generate-monthly-report"),
    },
    AutomationTaskType.MONITORING: {
        "default": (check_sync_status, "check_sync_status"),
        "check_sync_status": (check_sync_status, "check_sync_status"),
        "sync": (check_sync_status, "check_sync_status"),
        "check_task_health": (check_task_health, "check_task_health"),
        "health": (check_task_health, "check_task_health"),
    },
    AutomationTaskType.MAINTENANCE: {
        "default": (cleanup_old_logs, "cleanup_old_logs"),
        "cleanup_old_logs": (cleanup_old_logs, "cleanup_old_logs"),
        "cleanup": (cleanup_old_logs, "cleanup_old_logs"),
        "backup_automation_data": (backup_automation_data, "backup_automation_data"),
        "backup": (backup_automation_data, "backup_automation_data"),
    },
}


def resolve_celery_task(
    task_type: AutomationTaskType, task_name: Optional[str] = None
) -> Tuple[Any, str]:
    """
    작업 유형(task_type)과 세부 작업명(task_name)을 매핑하여
    실행할 Celery 태스크 객체와 표준 세부 작업명을 반환합니다.

    - task_name is None: 기본 작업 반환 (파라미터 생략 시)
    - task_name이 명시되었으나 빈 문자열("") 또는 공백인 경우:
      의도치 않은 기본 작업(파괴적일 수 있는 아카이빙/로그삭제 등) 실행 방지를 위해 400 Bad Request 반환
    """
    type_tasks = TASK_REGISTRY.get(task_type)
    if not type_tasks:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported automation task type: {task_type}",
        )

    # 1. task_name이 생략된 경우(None)에만 안전하게 기본 작업 반환
    if task_name is None:
        return type_tasks["default"]

    # 2. 명시적으로 전달되었으나 빈 문자열 또는 공백만 있는 경우 400 거부
    stripped = task_name.strip()
    if not stripped:
        available = sorted({name for name in type_tasks.keys() if name != "default"})
        raise HTTPException(
            status_code=400,
            detail=(
                f"task_name cannot be empty if specified. "
                f"Available task names for '{task_type.value}': {', '.join(available)}"
            ),
        )

    # 3. 대소문자 무관 정규화 매핑
    normalized = stripped.lower()
    if normalized in type_tasks:
        return type_tasks[normalized]

    available = sorted({name for name in type_tasks.keys() if name != "default"})
    raise HTTPException(
        status_code=400,
        detail=(
            f"Unknown task_name '{task_name}' for task_type '{task_type.value}'. "
            f"Available task names: {', '.join(available)}"
        ),
    )


@router.post(
    "/tasks/trigger",
    response_model=TaskTriggerResponse,
    status_code=202,
    summary="수동 자동화 작업 트리거",
)
def trigger_automation_task(
    task_type: AutomationTaskType = Query(..., description="작업 유형"),
    task_name: Optional[str] = Query(
        None, description="세부 작업명 (선택, 미지정 시 기본 태스크 실행)"
    ),
):
    """
    수동 자동화 작업 트리거

    - Celery 태스크를 수동으로 비동기 지연 실행(.delay())
    - task_name 생략 시 각 task_type별 기본 태스크 자동 선택
    - 브로커 연결 실패 시 503 Service Unavailable 반환
    - 트리거 성공 시 202 Accepted 및 Celery task_id 반환, automation_manager에 이력 기록
    """
    celery_task, resolved_task_name = resolve_celery_task(task_type, task_name)

    try:
        async_result = celery_task.delay()
        task_id = str(async_result.id)
    except Exception as exc:
        meta = build_meta(
            {
                "action": "trigger_automation_task",
                "task_type": task_type.value,
                "task_name": resolved_task_name,
            }
        )
        log_agent_error(logger, "Failed to dispatch Celery task to broker", exc, meta)
        raise HTTPException(
            status_code=503,
            detail="Celery task broker is unavailable or connection failed. Please ensure Redis/Celery worker is running.",
        ) from exc

    triggered_at = datetime.now(timezone.utc)

    # automation_manager에 트리거 이력 기록 (Pending 상태)
    try:
        automation_manager.record_task_trigger(
            task_type=task_type,
            task_name=resolved_task_name,
            celery_task_id=task_id,
            status=AutomationStatus.PENDING,
            details={
                "trigger": "manual_api",
                "triggered_at": triggered_at.isoformat(),
            },
        )
    except Exception as exc:
        meta = build_meta(
            {
                "action": "record_task_trigger_fallback",
                "task_id": task_id,
                "task_type": task_type.value,
            }
        )
        log_agent_error(
            logger,
            "Failed to record task trigger history to automation_manager",
            exc,
            meta,
        )

    logger.info(
        "Automation task successfully triggered: type=%s, name=%s, task_id=%s",
        task_type.value,
        resolved_task_name,
        task_id,
    )

    return TaskTriggerResponse(
        task_id=task_id,
        task_type=task_type,
        task_name=resolved_task_name,
        status="queued",
        message=f"Automation task '{resolved_task_name}' successfully triggered and queued.",
        triggered_at=triggered_at,
    )


# ============================================================================
# Watchdog Event Logs (Phase 6 - Automation Dashboard)
# ============================================================================


WatchdogEventType = Literal["created", "modified", "moved", "deleted"]
WatchdogEventStatus = Literal["pending", "completed", "failed"]


class WatchdogEvent(BaseModel):
    """Watchdog 이벤트 모델"""

    event_id: str = Field(..., description="이벤트 ID")
    timestamp: datetime = Field(..., description="발생 시각")
    event_type: WatchdogEventType = Field(..., description="이벤트 유형")
    file_path: str = Field(..., description="파일 경로")
    action: str = Field(..., description="트리거된 액션")
    status: WatchdogEventStatus = Field(..., description="처리 상태")


class WatchdogEventListResponse(BaseModel):
    """Watchdog 이벤트 목록 응답"""

    total: int = Field(..., description="전체 이벤트 수")
    events: List[WatchdogEvent] = Field(..., description="이벤트 목록")


ACTION_DEFAULTS = {
    "created": "Triggered Reclassification",
    "modified": "Updated Embedding",
    "moved": "Updated Embedding",
    "deleted": "Removed Index",
}


def _parse_watchdog_event_line(line_str: str, line_num: int) -> Optional[WatchdogEvent]:
    """
    단일 JSONL 라인을 파싱 및 정규화하여 WatchdogEvent 객체로 반환합니다.
    형식이 올바르지 않거나 검증 실패 시 None을 반환합니다.
    """
    try:
        data = json.loads(line_str)
        if not isinstance(data, dict):
            return None

        # 필수 타임스탬프 파싱 (ISO 8601 및 aware UTC 정규화)
        ts_raw = data.get("timestamp")
        if not ts_raw:
            return None

        ts_str = str(ts_raw).replace("Z", "+00:00")
        ts = datetime.fromisoformat(ts_str)
        ts = (
            ts.replace(tzinfo=timezone.utc)
            if ts.tzinfo is None
            else ts.astimezone(timezone.utc)
        )

        # event_type 정규화 및 검증
        event_type_raw = str(data.get("event_type", "")).strip().lower()
        if event_type_raw not in ("created", "modified", "moved", "deleted"):
            return None

        # status 정규화 및 검증
        status_raw = str(data.get("status", "completed")).strip().lower()
        if status_raw not in ("pending", "completed", "failed"):
            status_raw = "completed"

        # action 기본값 결정
        action_raw = data.get("action") or ACTION_DEFAULTS.get(
            event_type_raw, "Processed"
        )

        return WatchdogEvent(
            event_id=str(data.get("event_id") or f"evt_{line_num}"),
            timestamp=ts,
            event_type=event_type_raw,  # type: ignore[arg-type]
            file_path=str(
                data.get("file_path") or data.get("src_path") or data.get("path") or ""
            ),
            action=str(action_raw),
            status=status_raw,  # type: ignore[arg-type]
        )
    except (json.JSONDecodeError, ValidationError, KeyError, TypeError, ValueError):
        return None


def _read_watchdog_events(
    log_file: Path,
    event_type_filter: Optional[str] = None,
) -> List[WatchdogEvent]:
    """
    Watchdog 이벤트 로그 파일(JSONL)을 읽어 파싱, 필터링 및 최신순 정렬된 목록을 반환합니다.

    - 파일 미존재 시 빈 목록을 안전하게 반환합니다.
    - 손상된 JSON 또는 모델 유효성 검증 실패 라인은 스킵하고 요약 경고 로그를 남깁니다.
    - timestamp를 UTC 기준으로 안전하게 정규화하여 aware/naive 혼합 정렬 예외를 원천 방어합니다.
    - event_type 필터링(대소문자 무관)을 지원합니다.
    - 최신순 정렬 시 timestamp 내림차순(1차) 및 line_num 내림차순(2차)을 적용하여,
      타임스탬프가 동일한 경우 나중에 파일에 추가된 최신 레코드가 먼저 정렬되도록 보장합니다.
    """
    if not log_file.exists():
        logger.debug(
            "Watchdog event log file not found; returning empty list. path_exists=False"
        )
        return []

    raw_events: List[Tuple[WatchdogEvent, int]] = []
    parse_error_count = 0

    with open(log_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            event = _parse_watchdog_event_line(line_str, line_num)
            if event is None:
                parse_error_count += 1
            else:
                raw_events.append((event, line_num))

    if parse_error_count > 0:
        logger.warning(
            "Watchdog log parsing: %d line(s) skipped due to invalid format.",
            parse_error_count,
            extra={"skipped_lines": parse_error_count},
        )

    # event_type 필터링 (대소문자 무관)
    if event_type_filter and event_type_filter.strip():
        normalized_filter = event_type_filter.strip().lower()
        raw_events = [
            item for item in raw_events if item[0].event_type == normalized_filter
        ]

    # 최신순 정렬: 1차 timestamp 내림차순, 2차 line_num 내림차순 (나중에 추가된 항목 우선)
    raw_events.sort(key=lambda item: (item[0].timestamp, item[1]), reverse=True)
    return [item[0] for item in raw_events]


@router.get("/watchdog/events", response_model=WatchdogEventListResponse)
async def get_watchdog_events(
    limit: int = Query(50, ge=1, le=500, description="최대 반환 개수"),
    event_type: Optional[WatchdogEventType] = Query(
        None, description="이벤트 유형 필터 (created, modified, moved, deleted)"
    ),
) -> WatchdogEventListResponse:
    """
    Watchdog 이벤트 로그 조회

    - Obsidian Vault의 파일 변경 이벤트 로그 조회 (JSONL 실연동)
    - 최신순 정렬(동일 타임스탬프 시 추가 순서 보조 정렬), event_type 필터링 및 limit 제한 지원
    - 유효하지 않은 event_type 입력 시 422 유효성 검사 에러 반환
    - 대규모 파일 I/O 블로킹 방지를 위해 run_in_threadpool 사용
    """
    log_file = PathConfig.DATA_DIR / "watchdog" / "events.jsonl"

    try:
        events = await run_in_threadpool(_read_watchdog_events, log_file, event_type)
    except OSError as exc:
        log_agent_error(logger, "Failed to read watchdog event log file", exc)
        raise HTTPException(
            status_code=500,
            detail="Watchdog 이벤트 로그를 읽는 중 오류가 발생했습니다.",
        ) from exc

    total = len(events)
    sliced = events[:limit]

    logger.debug(
        "Watchdog events query: total=%d, event_type_filter=%s, returning=%d",
        total,
        event_type or "all",
        len(sliced),
    )

    return WatchdogEventListResponse(total=total, events=sliced)


# ============================================================================
# Dashboard Summary (Phase 6 - General Dashboard)
# ============================================================================


class DashboardSummary(BaseModel):
    """대시보드 요약 정보"""

    total_files: int = Field(..., description="전체 파일 수")
    total_classifications: int = Field(..., description="전체 분류 수")
    total_conflicts: int = Field(..., description="전체 충돌 수")
    automation_tasks_today: int = Field(..., description="오늘 실행된 자동화 작업 수")
    active_rules: int = Field(..., description="활성화된 자동화 규칙 수")
    pending_tasks: int = Field(..., description="실행 중이거나 대기 중인 작업 수")
    sync_status: str = Field(..., description="동기화 상태")
    last_sync: Optional[str] = Field(None, description="마지막 동기화 시각")


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary():
    """
    대시보드 요약 정보 조회

    - 전체 파일 수, 분류 수, 충돌 수, 활성 규칙 수, 대기 작업 수 등
    - AutomationManager 실데이터를 기반으로 모든 지표 집계
    """
    from datetime import date

    from backend.models.automation import AutomationStatus

    # 오늘 날짜 실행된 작업 수 집계
    today = date.today()
    all_logs = automation_manager.get_automation_logs(limit=1000)
    tasks_today = sum(
        log.started_at.date() == today and log.status == AutomationStatus.COMPLETED
        for log in all_logs
    )

    # 활성 자동화 규칙 수: AutomationManager JSONL 기반 실집계 (I/O 에러 안전 방어)
    try:
        all_rules = automation_manager.get_automation_rules()
        active_rules = sum(rule.is_active for rule in all_rules)
    except OSError as exc:
        logger.warning(
            "Failed to count active automation rules due to I/O error: %s", exc
        )
        active_rules = 0

    # 실행 중(RUNNING) 또는 대기 중(PENDING) 작업 수: AutomationManager 로그 실집계
    try:
        running_logs = automation_manager.get_automation_logs(
            limit=500, status=AutomationStatus.RUNNING
        )
        pending_logs = automation_manager.get_automation_logs(
            limit=500, status=AutomationStatus.PENDING
        )
        pending_tasks = len(running_logs) + len(pending_logs)
    except OSError as exc:
        logger.warning(
            "Failed to count pending/running tasks due to I/O error: %s", exc
        )
        pending_tasks = 0

    # Vault 파일 수: mcp_config 기반 실제 카운트 (파일 I/O 에러 안전 방어)
    from pathlib import Path as _Path

    from backend.config.mcp_config import mcp_config

    vault_path = (
        _Path(mcp_config.obsidian.vault_path)
        if mcp_config.obsidian.vault_path
        else None
    )
    total_files = 0
    if vault_path and vault_path.exists():
        try:
            total_files = len(list(vault_path.rglob("*.md")))
        except OSError as exc:
            logger.warning(
                "Failed to count markdown files in vault due to I/O error: %s", exc
            )

    # 분류 수: reclassification 이력 사용
    reclass_records = automation_manager.get_reclassification_history(limit=10000)
    total_classifications = len(reclass_records)

    # 충돌 수: 충돌 로그 JSONL 파일 실집계
    conflict_log = PathConfig.DATA_DIR / "sync_logs" / "detected_conflicts.jsonl"
    total_conflicts = 0
    if conflict_log.exists():
        try:
            with open(conflict_log, "r", encoding="utf-8") as f:
                total_conflicts = sum(bool(line.strip()) for line in f)
        except OSError:
            total_conflicts = 0

    # 동기화 상태
    sync_status = (
        "Connected" if (vault_path and vault_path.exists()) else "Disconnected"
    )

    # last_sync: SyncMapManager에서 전체 매핑 기준 최신 동기화 시각 실연동
    map_manager = get_sync_map_manager()
    latest_sync_dt = map_manager.get_latest_sync_time()
    last_sync = latest_sync_dt.isoformat() if latest_sync_dt is not None else None

    return DashboardSummary(
        total_files=total_files,
        total_classifications=total_classifications,
        total_conflicts=total_conflicts,
        automation_tasks_today=tasks_today,
        active_rules=active_rules,
        pending_tasks=pending_tasks,
        sync_status=sync_status,
        last_sync=last_sync,
    )

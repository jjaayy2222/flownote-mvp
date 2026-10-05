# backend/api/endpoints/automation.py

"""
Automation API Endpoints
자동화 작업 로그, 규칙, 이력 조회 및 관리 API
"""

import logging
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from fastapi import Query
from pydantic import BaseModel, Field

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
    except ValueError:
        raise HTTPException(status_code=409, detail="Rule with this ID already exists.")
    except OSError:
        raise HTTPException(status_code=500, detail="Failed to save automation rule.")


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
    except OSError:
        raise HTTPException(status_code=500, detail="Failed to update automation rule.")


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
    except OSError:
        raise HTTPException(status_code=500, detail="Failed to delete automation rule.")


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


@router.post("/tasks/trigger", status_code=202)
def trigger_automation_task(
    task_type: AutomationTaskType = Query(..., description="작업 유형")
):
    """
    수동 자동화 작업 트리거

    - Celery 태스크를 수동으로 실행
    - 현재는 미구현 (Celery 연동 필요)
    """
    # TODO: Celery 태스크 트리거 구현
    # from backend.celery_app.tasks import ...
    # task.delay()

    raise HTTPException(
        status_code=501,
        detail=f"Manual task triggering not implemented yet for {task_type.value}",
    )


# ============================================================================
# Watchdog Event Logs (Phase 6 - Automation Dashboard)
# ============================================================================


class WatchdogEvent(BaseModel):
    """Watchdog 이벤트 모델"""

    event_id: str = Field(..., description="이벤트 ID")
    timestamp: datetime = Field(..., description="발생 시각")
    event_type: Literal["created", "modified", "moved", "deleted"] = Field(
        ..., description="이벤트 유형"
    )
    file_path: str = Field(..., description="파일 경로")
    action: str = Field(..., description="트리거된 액션")
    status: Literal["pending", "completed", "failed"] = Field(
        ..., description="처리 상태"
    )


class WatchdogEventListResponse(BaseModel):
    """Watchdog 이벤트 목록 응답"""

    total: int = Field(..., description="전체 이벤트 수")
    events: List[WatchdogEvent] = Field(..., description="이벤트 목록")


@router.get("/watchdog/events", response_model=WatchdogEventListResponse)
def get_watchdog_events(
    limit: int = Query(50, ge=1, le=500, description="최대 반환 개수"),
    event_type: Optional[str] = Query(None, description="이벤트 유형 필터"),
):
    """
    Watchdog 이벤트 로그 조회

    - Obsidian Vault의 파일 변경 이벤트 로그
    - 예: [Obsidian] File Created: "Idea.md" -> Triggered Reclassification
    """
    # TODO: 실제로는 파일 시스템 또는 DB에서 조회
    # 현재는 Placeholder 데이터 반환
    events = [
        WatchdogEvent(
            event_id="evt_001",
            timestamp=datetime.fromisoformat("2025-12-25T19:00:00"),
            event_type="created",
            file_path="Idea.md",
            action="Triggered Reclassification",
            status="completed",
        ),
        WatchdogEvent(
            event_id="evt_002",
            timestamp=datetime.fromisoformat("2025-12-25T18:55:00"),
            event_type="modified",
            file_path="Project_Plan.md",
            action="Updated Embedding",
            status="completed",
        ),
    ]

    if event_type:
        events = [e for e in events if e.event_type == event_type]

    return WatchdogEventListResponse(total=len(events), events=events[:limit])


# ============================================================================
# Dashboard Summary (Phase 6 - General Dashboard)
# ============================================================================


class DashboardSummary(BaseModel):
    """대시보드 요약 정보"""

    total_files: int = Field(..., description="전체 파일 수")
    total_classifications: int = Field(..., description="전체 분류 수")
    total_conflicts: int = Field(..., description="전체 충돌 수")
    automation_tasks_today: int = Field(..., description="오늘 실행된 자동화 작업 수")
    sync_status: str = Field(..., description="동기화 상태")
    last_sync: Optional[str] = Field(None, description="마지막 동기화 시각")


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary():
    """
    대시보드 요약 정보 조회

    - 전체 파일 수, 분류 수, 충돌 수 등
    - AutomationManager 로그 실데이터를 기반으로 집계
    """
    from datetime import date

    from backend.models.automation import AutomationStatus

    # 오늘 날짜 실행된 작업 수 집계
    today = date.today()
    all_logs = automation_manager.get_automation_logs(limit=1000)
    tasks_today = sum(
        1
        for log in all_logs
        if log.started_at.date() == today and log.status == AutomationStatus.COMPLETED
    )

    # Vault 파일 수: mcp_config 기반 실제 카운트
    from pathlib import Path as _Path

    from backend.config.mcp_config import mcp_config

    vault_path = (
        _Path(mcp_config.obsidian.vault_path)
        if mcp_config.obsidian.vault_path
        else None
    )
    total_files = (
        len(list(vault_path.rglob("*.md"))) if vault_path and vault_path.exists() else 0
    )

    # 분류 수: reclassification 이력 사용
    reclass_records = automation_manager.get_reclassification_history(limit=10000)
    total_classifications = len(reclass_records)

    # 충돌 수: archiving 이력 기반 집계 (충돌 로그 JSONL 파일이 연동될 때까지는 0)
    from backend.config import PathConfig

    conflict_log = PathConfig.DATA_DIR / "sync_logs" / "detected_conflicts.jsonl"
    total_conflicts = 0
    if conflict_log.exists():
        try:
            with open(conflict_log, "r", encoding="utf-8") as f:
                total_conflicts = sum(1 for line in f if line.strip())
        except OSError:
            total_conflicts = 0

    # 동기화 상태
    sync_status = (
        "Connected" if (vault_path and vault_path.exists()) else "Disconnected"
    )

    # last_sync: SyncMapManager 연동 전까지 None
    last_sync = None

    return DashboardSummary(
        total_files=total_files,
        total_classifications=total_classifications,
        total_conflicts=total_conflicts,
        automation_tasks_today=tasks_today,
        sync_status=sync_status,
        last_sync=last_sync,
    )

# backend/api/endpoints/automation.py

"""
Automation API Endpoints
자동화 작업 로그, 규칙, 이력 조회 및 관리 API
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Path as PathParam
from pydantic import BaseModel, Field

from backend.models.automation import (
    AutomationLog,
    AutomationRule,
    AutomationTaskType,
    AutomationStatus,
    ReclassificationRecord,
    ArchivingRecord,
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
async def get_automation_logs(
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
async def get_automation_log_detail(
    log_id: str = PathParam(..., description="로그 ID")
):
    """
    자동화 로그 상세 조회

    - 특정 로그의 상세 정보 조회
    """
    log = automation_manager.get_automation_log_by_id(log_id)

    if log is None:
        raise HTTPException(status_code=404, detail=f"Log not found: {log_id}")

    return log


@router.get("/rules", response_model=AutomationRuleListResponse)
async def get_automation_rules():
    """
    자동화 규칙 목록 조회

    - 현재는 파일 기반 저장소가 없으므로 빈 목록 반환
    - 향후 DB 연동 시 구현 예정
    """
    rules = automation_manager.get_automation_rules()
    return AutomationRuleListResponse(total=len(rules), rules=rules)


@router.post("/rules", response_model=AutomationRule, status_code=201)
async def create_automation_rule(rule: AutomationRule):
    """
    자동화 규칙 생성

    - 새로운 자동화 규칙 생성
    - 현재는 미구현 (DB 필요)
    """
    try:
        return automation_manager.create_automation_rule(rule)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@router.put("/rules/{rule_id}", response_model=AutomationRule)
async def update_automation_rule(
    rule: AutomationRule, rule_id: str = PathParam(..., description="규칙 ID")
):
    """
    자동화 규칙 수정

    - 기존 규칙 수정
    - 현재는 미구현 (DB 필요)
    """
    try:
        result = automation_manager.update_automation_rule(rule_id, rule)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
        return result
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_automation_rule(rule_id: str = PathParam(..., description="규칙 ID")):
    """
    자동화 규칙 삭제

    - 기존 규칙 삭제
    - 현재는 미구현 (DB 필요)
    """
    try:
        success = automation_manager.delete_automation_rule(rule_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@router.get("/reclassifications", response_model=ReclassificationHistoryResponse)
async def get_reclassification_history(
    limit: int = Query(100, ge=1, le=1000, description="최대 반환 개수")
):
    """
    재분류 이력 조회

    - 최근 재분류 작업 이력 조회
    """
    records = automation_manager.get_reclassification_history(limit=limit)
    return ReclassificationHistoryResponse(total=len(records), records=records)


@router.get("/archives", response_model=ArchivingHistoryResponse)
async def get_archiving_history(
    limit: int = Query(100, ge=1, le=1000, description="최대 반환 개수")
):
    """
    아카이브 이력 조회

    - 최근 아카이브 작업 이력 조회
    """
    records = automation_manager.get_archiving_history(limit=limit)
    return ArchivingHistoryResponse(total=len(records), records=records)


@router.post("/tasks/trigger", status_code=202)
async def trigger_automation_task(
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
    timestamp: str = Field(..., description="발생 시각")
    event_type: str = Field(
        ..., description="이벤트 유형 (created, modified, moved, deleted)"
    )
    file_path: str = Field(..., description="파일 경로")
    action: str = Field(..., description="트리거된 액션")
    status: str = Field(..., description="처리 상태 (pending, completed, failed)")


class WatchdogEventListResponse(BaseModel):
    """Watchdog 이벤트 목록 응답"""

    total: int = Field(..., description="전체 이벤트 수")
    events: List[WatchdogEvent] = Field(..., description="이벤트 목록")


@router.get("/watchdog/events", response_model=WatchdogEventListResponse)
async def get_watchdog_events(
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
            timestamp="2025-12-25T19:00:00",
            event_type="created",
            file_path="Idea.md",
            action="Triggered Reclassification",
            status="completed",
        ),
        WatchdogEvent(
            event_id="evt_002",
            timestamp="2025-12-25T18:55:00",
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
async def get_dashboard_summary():
    """
    대시보드 요약 정보 조회

    - 전체 파일 수, 분류 수, 충돌 수 등
    - Summary Card에 표시될 정보
    """
    # TODO: 실제 데이터 집계
    # - 파일 시스템에서 파일 수 계산
    # - classification_log.csv에서 분류 수 계산
    # - ExternalSyncLog에서 충돌 수 계산
    # - AutomationLog에서 오늘 작업 수 계산

    return DashboardSummary(
        total_files=150,
        total_classifications=320,
        total_conflicts=5,
        automation_tasks_today=12,
        sync_status="Connected",
        last_sync="2025-12-25T18:50:00",
    )

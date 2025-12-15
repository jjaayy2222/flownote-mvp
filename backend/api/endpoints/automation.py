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
    task_type: Optional[str] = Query(None, description="작업 유형 필터"),
    status: Optional[str] = Query(None, description="상태 필터"),
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
    # TODO: DB 연동 후 규칙 저장 구현
    raise HTTPException(
        status_code=501, detail="Rule creation not implemented yet (DB required)"
    )


@router.put("/rules/{rule_id}", response_model=AutomationRule)
async def update_automation_rule(
    rule_id: str = PathParam(..., description="규칙 ID"), rule: AutomationRule = None
):
    """
    자동화 규칙 수정

    - 기존 규칙 수정
    - 현재는 미구현 (DB 필요)
    """
    # TODO: DB 연동 후 규칙 수정 구현
    raise HTTPException(
        status_code=501, detail="Rule update not implemented yet (DB required)"
    )


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_automation_rule(rule_id: str = PathParam(..., description="규칙 ID")):
    """
    자동화 규칙 삭제

    - 기존 규칙 삭제
    - 현재는 미구현 (DB 필요)
    """
    # TODO: DB 연동 후 규칙 삭제 구현
    raise HTTPException(
        status_code=501, detail="Rule deletion not implemented yet (DB required)"
    )


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
    task_type: str = Query(
        ..., description="작업 유형 (reclassification, archiving, reporting)"
    )
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
        status_code=501, detail="Manual task triggering not implemented yet"
    )

# backend/models/automation.py

from enum import Enum
from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel, Field


class AutomationTaskType(str, Enum):
    """자동화 작업 유형"""

    RECLASSIFICATION = "reclassification"  # 재분류
    ARCHIVING = "archiving"  # 자동 아카이빙
    REPORTING = "reporting"  # 리포트 생성
    MONITORING = "monitoring"  # 시스템/동기화 모니터링
    MAINTENANCE = "maintenance"  # 로그 정리 등 유지보수


class AutomationStatus(str, Enum):
    """작업 실행 상태"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AutomationRule(BaseModel):
    """사용자가 정의한 자동화 규칙 (DB 저장용)"""

    rule_id: str = Field(..., description="규칙 고유 ID")
    name: str = Field(..., description="규칙 이름")
    task_type: AutomationTaskType = Field(..., description="적용될 작업 유형")
    conditions: Dict = Field(default_factory=dict, description="실행 조건 (JSON)")
    actions: Dict = Field(default_factory=dict, description="수행 동작 (JSON)")
    is_active: bool = Field(True, description="활성화 여부")
    created_at: datetime = Field(default_factory=datetime.now)


class AutomationLog(BaseModel):
    """자동화 작업 실행 로그"""

    log_id: str = Field(..., description="로그 고유 ID (UUID)")
    task_type: AutomationTaskType = Field(..., description="작업 유형")
    task_name: str = Field(..., description="세부 작업명 (e.g., daily-reclassify)")
    celery_task_id: str = Field(..., description="Celery Task ID")

    status: AutomationStatus = Field(AutomationStatus.PENDING, description="실행 상태")

    # 실행 결과 요약
    files_processed: int = Field(0, description="처리된 파일 수")
    files_updated: int = Field(0, description="변경/이동된 파일 수")
    files_archived: int = Field(0, description="아카이브된 파일 수")
    errors_count: int = Field(0, description="발생한 에러 수")

    # 상세 결과 (JSON)
    details: Optional[Dict] = Field(default_factory=dict, description="상세 실행 결과")

    # 타이밍
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    duration_seconds: float = Field(0.0, description="소요 시간(초)")


class ReclassificationRecord(BaseModel):
    """개별 파일 재분류 기록"""

    record_id: str
    automation_log_id: str = Field(..., description="연관된 AutomationLog ID")
    file_path: str
    old_category: str
    new_category: str
    confidence_score: float
    reason: Optional[str] = None
    processed_at: datetime = Field(default_factory=datetime.now)


class ArchivingRecord(BaseModel):
    """개별 파일 아카이빙 기록"""

    record_id: str
    automation_log_id: str = Field(..., description="연관된 AutomationLog ID")
    file_path: str
    archive_path: str
    reason: str  # e.g., "inactive_for_30_days"
    archived_at: datetime = Field(default_factory=datetime.now)

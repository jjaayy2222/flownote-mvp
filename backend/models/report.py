# backend/models/report.py

from enum import Enum
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, root_validator


class ReportType(str, Enum):
    """리포트 유형"""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ReportMetric(BaseModel):
    """리포트 내 개별 메트릭 항목"""

    metric_name: str = Field(..., description="메트릭 이름")
    value: Any = Field(..., description="메트릭 값 (int, float, dict 등)")
    unit: Optional[str] = Field(None, description="단위 (e.g., 'count', 'MB')")
    description: Optional[str] = Field(None, description="메트릭 설명")


class Report(BaseModel):
    """자동화 리포트 모델"""

    report_id: str = Field(..., description="리포트 고유 ID (UUID)")
    title: str = Field(..., description="리포트 제목")
    report_type: ReportType = Field(..., description="리포트 유형")

    # 리포트 대상 기간
    period_start: datetime = Field(..., description="집계 시작 일시")
    period_end: datetime = Field(..., description="집계 종료 일시")

    # 내용
    summary: str = Field(..., description="리포트 요약")
    insights: List[str] = Field(default_factory=list, description="주요 인사이트 목록")
    recommendations: List[str] = Field(
        default_factory=list, description="시스템 권장 사항"
    )

    # 상세 데이터
    metrics: Dict[str, "ReportMetric"] = Field(
        default_factory=dict, description="상세 메트릭 데이터 (키별 ReportMetric 매핑)"
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="생성 일시 (UTC)",
    )

    @root_validator
    def validate_period_range(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        period_start = values.get("period_start")
        period_end = values.get("period_end")

        if period_start is not None and period_end is not None:
            if period_end < period_start:
                raise ValueError(
                    "period_end must be greater than or equal to period_start"
                )

        return values

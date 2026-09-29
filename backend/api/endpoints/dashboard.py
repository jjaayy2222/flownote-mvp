# backend/api/endpoints/dashboard.py

"""Dashboard Integration Endpoints"""

import logging
from typing import Optional

from fastapi import APIRouter

from backend.agent.error_utils import build_meta, log_agent_error
from backend.dashboard.dashboard_core import MetadataAggregator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_dashboard_service = None


def get_dashboard_service() -> Optional[MetadataAggregator]:
    """MetadataAggregator 인스턴스 반환 (Lazy Loading). 초기화 실패 시 None 반환."""
    global _dashboard_service
    if _dashboard_service is None:
        try:
            _dashboard_service = MetadataAggregator()
            logger.info("✅ MetadataAggregator loaded successfully")
        except Exception as e:
            meta = build_meta({"action": "load_dashboard_service"})
            log_agent_error(
                logger,
                "[Dashboard] MetadataAggregator 초기화 실패",
                e,
                meta,
                include_traceback=True,
            )
            _dashboard_service = None
    return _dashboard_service


@router.get("/status")
async def get_dashboard_status():
    """대시보드 상태"""
    if dashboard := get_dashboard_service():
        # MetadataAggregator의 메소드 사용
        return {"status": "ready", "statistics": dashboard.get_file_statistics()}
    return {"status": "ready"}


@router.get("/metrics")
async def get_metrics():
    """메트릭 조회"""
    if dashboard := get_dashboard_service():
        return {
            "file_statistics": dashboard.get_file_statistics(),
            "para_breakdown": dashboard.get_para_breakdown(),
            "keyword_categories": dashboard.get_keyword_categories(),
        }
    return {"total_files": 0, "classified": 0}


@router.get("/keywords")
async def get_top_keywords(top_n: int = 10):
    """상위 키워드"""
    if dashboard := get_dashboard_service():
        return {"top_keywords": dashboard.get_top_keywords(top_n)}
    return {"top_keywords": []}


@router.get("/stats")
async def get_advanced_stats():
    """고급 통계 차트 데이터"""
    if dashboard := get_dashboard_service():
        return {
            "activity_heatmap": dashboard.get_activity_heatmap(),
            "weekly_trend": dashboard.get_weekly_trend(),
            "para_distribution": dashboard.get_para_breakdown(),
        }
    return {"activity_heatmap": [], "weekly_trend": [], "para_distribution": {}}

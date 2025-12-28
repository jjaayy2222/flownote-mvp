# backend/api/endpoints/dashboard.py

"""Dashboard Integration Endpoints"""

from fastapi import APIRouter
from backend.dashboard.dashboard_core import MetadataAggregator

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_dashboard_service = None


def get_dashboard_service() -> MetadataAggregator:
    """MetadataAggregator 인스턴스 반환 (Lazy Loading)"""
    global _dashboard_service
    if _dashboard_service is None:
        try:
            _dashboard_service = MetadataAggregator()
            print("✅ MetadataAggregator loaded successfully")
        except Exception as e:
            print(f"⚠️ Dashboard load failed: {e}")
            _dashboard_service = None
    return _dashboard_service


@router.get("/status")
async def get_dashboard_status():
    """대시보드 상태"""
    dashboard = get_dashboard_service()
    if dashboard:
        # MetadataAggregator의 메소드 사용
        return {"status": "ready", "statistics": dashboard.get_file_statistics()}
    return {"status": "ready"}


@router.get("/metrics")
async def get_metrics():
    """메트릭 조회"""
    dashboard = get_dashboard_service()
    if dashboard:
        return {
            "file_statistics": dashboard.get_file_statistics(),
            "para_breakdown": dashboard.get_para_breakdown(),
            "keyword_categories": dashboard.get_keyword_categories(),
        }
    return {"total_files": 0, "classified": 0}


@router.get("/keywords")
async def get_top_keywords(top_n: int = 10):
    """상위 키워드"""
    dashboard = get_dashboard_service()
    if dashboard:
        return {"top_keywords": dashboard.get_top_keywords(top_n)}
    return {"top_keywords": []}


@router.get("/stats")
async def get_advanced_stats():
    """고급 통계 차트 데이터"""
    dashboard = get_dashboard_service()
    if dashboard:
        return {
            "activity_heatmap": dashboard.get_activity_heatmap(),
            "weekly_trend": dashboard.get_weekly_trend(),
            "para_distribution": dashboard.get_para_breakdown(),
        }
    return {"activity_heatmap": [], "weekly_trend": [], "para_distribution": {}}

"""
Celery 애플리케이션 및 스케줄러(Beat) 진입점.

이 모듈은 FlowNote MVP의 백그라운드 작업을 조율하는 메인 Celery 앱 인스턴스를 생성하고,
주기적인 백그라운드 태스크(Beat Schedule)를 정의합니다. 설정은 `CeleryConfig`에서 로드하며,
`tasks` 패키지 내의 태스크들을 자동으로 검색하여 등록합니다.

Entry point for the Celery application and scheduler (Beat).

This module creates the main Celery app instance orchestrating background tasks
for FlowNote MVP, and defines periodic background tasks (Beat Schedule). It loads
configurations from `CeleryConfig` and automatically discovers and registers tasks
from the `tasks` package.
"""

from celery import Celery
from celery.schedules import crontab

from backend.celery_app.config import CeleryConfig

# Celery App 인스턴스 초기화
# Initialize the Celery App instance
app = Celery("flownote")

# CeleryConfig 클래스 기반 설정 적용
# Apply configurations based on the CeleryConfig class
app.config_from_object(CeleryConfig)

# 태스크 자동 발견 (Auto-discover Tasks)
# 'backend.celery_app.tasks.__init__.py'에서 명시적으로 임포트된 태스크들을 로드합니다.
# Automatically discover and load tasks explicitly imported in 'backend.celery_app.tasks.__init__.py'.
app.autodiscover_tasks(["backend.celery_app"])

# Beat Schedule 정의
# Define the Beat Schedule for periodic tasks
app.conf.beat_schedule = {
    # 1. 재분류 (매일 자정) / Reclassification (Daily at Midnight)
    "daily-reclassification": {
        "task": "backend.celery_app.tasks.reclassification.daily_reclassify_tasks",
        "schedule": crontab(hour=0, minute=0),
    },
    # 2. 심층 재분류 (매주 일요일 새벽 2시) / Deep Reclassification (Weekly on Sunday at 2 AM)
    "weekly-reclassification": {
        "task": "backend.celery_app.tasks.reclassification.weekly_reclassify_tasks",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),
    },
    # 3. 자동 아카이브 (매일 새벽 3시) / Auto Archiving (Daily at 3 AM)
    "daily-archiving": {
        "task": "backend.celery_app.tasks.archiving.auto_archive_tasks",
        "schedule": crontab(hour=3, minute=0),
    },
    # 4. 주간 리포트 생성 (매주 월요일 아침 9시) / Weekly Report Generation (Weekly on Monday at 9 AM)
    "weekly-report": {
        "task": "backend.celery_app.tasks.reporting.generate_weekly_report",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
    },
    # 5. 월간 리포트 생성 (매월 1일 아침 9시) / Monthly Report Generation (Monthly on the 1st at 9 AM)
    "monthly-report": {
        "task": "backend.celery_app.tasks.reporting.generate_monthly_report",
        "schedule": crontab(hour=9, minute=0, day_of_month="1"),
    },
    # 6. 동기화 상태 모니터링 (매시간 정각) / Sync Status Monitoring (Hourly on the hour)
    "monitor-sync-status": {
        "task": "backend.celery_app.tasks.monitoring.check_sync_status",
        "schedule": crontab(minute=0),
    },
    # 7. 로그 및 임시 파일 정리 (매주 일요일 새벽 4시) / Cleanup Logs and Temp Files (Weekly on Sunday at 4 AM)
    "cleanup-logs": {
        "task": "backend.celery_app.tasks.maintenance.cleanup_old_logs",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),
    },
    # 8. 고립된 노트 스캔 (매일 새벽 5시) / Orphan Notes Scan (Daily at 5 AM)
    "daily-orphan-notes-scan": {
        "task": "backend.celery_app.tasks.graph.detect_orphan_notes_for_all_users",
        "schedule": crontab(hour=5, minute=0),
    },
}

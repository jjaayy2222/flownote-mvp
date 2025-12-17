# backend/celery_app/celery.py

from celery import Celery
from celery.schedules import crontab
from backend.celery_app.config import CeleryConfig

# Celery App 초기화
app = Celery("flownote")

# 설정 로드
app.config_from_object(CeleryConfig)

# 태스크 자동 발견 (Auto-discover Tasks)
# 'backend.celery_app' 앱 내의 tasks 모듈(패키지)을 자동으로 찾아 로드합니다.
# backend/celery_app/tasks/__init__.py에서 명시적으로 임포트된 태스크들이 등록됩니다.
app.autodiscover_tasks(["backend.celery_app"])

# Beat Schedule 정의
app.conf.beat_schedule = {
    # 1. 재분류 (Daily - 매일 자정)
    "daily-reclassification": {
        "task": "backend.celery_app.tasks.reclassification.daily_reclassify_tasks",
        "schedule": crontab(hour=0, minute=0),
    },
    # 2. 재분류 심화 (Weekly - 매주 일요일 새벽 2시)
    "weekly-reclassification": {
        "task": "backend.celery_app.tasks.reclassification.weekly_reclassify_tasks",
        "schedule": crontab(hour=2, minute=0, day_of_week=0),
    },
    # 3. 자동 아카이브 (Daily - 매일 새벽 3시)
    "daily-archiving": {
        "task": "backend.celery_app.tasks.archiving.auto_archive_tasks",
        "schedule": crontab(hour=3, minute=0),
    },
    # 4. 주간 리포트 (Weekly - 매주 월요일 아침 9시)
    "weekly-report": {
        "task": "backend.celery_app.tasks.reporting.generate_weekly_report",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
    },
    # 5. 월간 리포트 (Monthly - 매월 1일 아침 9시)
    "monthly-report": {
        "task": "backend.celery_app.tasks.reporting.generate_monthly_report",
        "schedule": crontab(hour=9, minute=0, day_of_month="1"),
    },
    # 6. 동기화 상태 모니터링 (Hourly - 매시간 정각)
    "monitor-sync-status": {
        "task": "backend.celery_app.tasks.monitoring.check_sync_status",
        "schedule": crontab(minute=0),
    },
    # 7. 로그 및 임시 파일 정리 (Weekly - 매주 일요일 새벽 4시)
    "cleanup-logs": {
        "task": "backend.celery_app.tasks.maintenance.cleanup_old_logs",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),
    },
}

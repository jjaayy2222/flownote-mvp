# backend/celery_app/celery.py

import pkgutil
from celery import Celery
from celery.schedules import crontab
from backend.celery_app.config import CeleryConfig
import backend.celery_app.tasks

# Celery App 초기화
# 'flownote'는 프로젝트의 고유 이름입니다.
app = Celery("flownote")

# Config Object로부터 설정 로드
app.config_from_object(CeleryConfig)

# 태스크 모듈 자동 발견 (Auto-discover Task Modules)
# backend/celery_app/tasks 패키지 내의 모든 모듈을 동적으로 발견하여 등록합니다.
# 이를 통해 새로운 태스크 파일이 추가되어도 코드를 수정할 필요가 없습니다.
task_modules = [
    f"backend.celery_app.tasks.{name}"
    for _, name, _ in pkgutil.iter_modules(backend.celery_app.tasks.__path__)
]
app.conf.update(include=task_modules)

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

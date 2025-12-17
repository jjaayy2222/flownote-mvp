# backend/celery_app/config.py

import os


class CeleryConfig:
    # Broker & Backend Settings
    # RabbitMQ를 사용하지 않고 Redis를 Broker와 Backend로 모두 사용합니다.
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # Timezone Setting (KST)
    timezone = "Asia/Seoul"
    enable_utc = False

    # Task & Result Serialization
    task_serializer = "json"
    result_serializer = "json"
    accept_content = ["json"]

    # Worker Settings
    # Prefetch Multiplier: 한 번에 가져올 태스크 수 (1로 설정하여 공정하게 분배)
    worker_prefetch_multiplier = 1
    # Max Tasks Per Child: 메모리 누수 방지를 위해 일정 작업 후 워커 프로세스 재시작
    worker_max_tasks_per_child = 50

    # Logging
    worker_hijack_root_logger = False

"""
Celery 백그라운드 워커 설정 모듈.

이 모듈은 FlowNote MVP의 백그라운드 태스크 처리를 위한 Celery 구성을 정의합니다.
Redis를 메시지 브로커 및 결과 저장소로 활용하며, 워커 동작(Prefetch, Max Tasks)을 최적화합니다.

Configuration module for the Celery background worker.

This module defines the Celery configuration for background task processing in FlowNote MVP.
It utilizes Redis as both the message broker and result backend, and optimizes worker behavior.
"""

import os


class CeleryConfig:
    """
    Celery 워커 기본 설정 클래스.

    브로커 URL, 직렬화 방식, 워커의 메모리 누수 방지 등 핵심 설정을 관리합니다.

    Base configuration class for the Celery worker.

    Manages core settings such as broker URL, serialization methods, and
    worker memory leak prevention.

    Attributes:
        broker_url (str): 메시지 브로커 연결 URL (기본값: Redis).
            Message broker connection URL (default: Redis).
        result_backend (str): 태스크 결과 저장소 연결 URL (기본값: Redis).
            Task result backend connection URL (default: Redis).
        timezone (str): 워커 및 스케줄러 시간대 (기본값: Asia/Seoul).
            Timezone for the worker and scheduler (default: Asia/Seoul).
        enable_utc (bool): UTC 사용 여부 (기본값: False).
            Whether to enable UTC (default: False).
        task_serializer (str): 태스크 페이로드 직렬화 포맷 (기본값: json).
            Task payload serialization format (default: json).
        result_serializer (str): 결과 페이로드 직렬화 포맷 (기본값: json).
            Result payload serialization format (default: json).
        accept_content (list[str]): 허용되는 직렬화 콘텐츠 타입.
            Allowed serialization content types.
        worker_prefetch_multiplier (int): 워커가 한 번에 미리 가져올 태스크 수.
            1로 설정하여 태스크를 워커 간 공정하게 분배합니다.
            Number of tasks a worker prefetches at a time.
            Set to 1 to distribute tasks fairly among workers.
        worker_max_tasks_per_child (int): 프로세스 재시작 전 처리할 최대 태스크 수.
            메모리 누수를 방지하기 위해 50으로 제한합니다.
            Maximum number of tasks processed before restarting the process.
            Limited to 50 to prevent memory leaks.
        worker_hijack_root_logger (bool): Celery가 루트 로거를 가로채는지 여부.
            기존 로깅 설정을 유지하기 위해 False로 설정합니다.
            Whether Celery hijacks the root logger.
            Set to False to preserve existing logging configurations.
    """

    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    timezone = "Asia/Seoul"
    enable_utc = False

    task_serializer = "json"
    result_serializer = "json"
    accept_content = ["json"]

    worker_prefetch_multiplier = 1
    worker_max_tasks_per_child = 50

    worker_hijack_root_logger = False

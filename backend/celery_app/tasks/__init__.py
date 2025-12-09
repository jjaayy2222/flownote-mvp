# backend/celery_app/tasks/__init__.py

# 태스크 모듈 명시적 등록
# autodiscover_tasks가 이 패키지(backend.celery_app.tasks)를 임포트할 때,
# 아래의 서브 모듈들도 함께 임포트되어 태스크가 등록됩니다.
# 새로운 태스크 파일을 생성하면 여기에 추가해 주세요.

from . import (
    reclassification,
    archiving,
    reporting,
    monitoring,
    maintenance,
)

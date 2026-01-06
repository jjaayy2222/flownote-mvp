# [NOTICE] 태스크 모듈 등록 가이드
# 새로운 태스크 파일(모듈)을 생성했다면, 반드시 아래 리스트에 추가해야 합니다.
# Celery의 autodiscover_tasks는 이 파일을 최초 진입점으로 사용하므로,
# 여기에 명시적으로 임포트되지 않은 모듈의 태스크는 실행되지 않습니다. (Silent Failure 방지)

from . import (
    reclassification,
    archiving,
    reporting,
    monitoring,
    maintenance,
    classification,  # Added classification task
)

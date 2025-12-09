# backend/celery_app/tasks/__init__.py

import pkgutil
import importlib
from pathlib import Path

# 현재 패키지(tasks) 내의 모든 모듈을 동적으로 발견하여 임포트합니다.
# 이를 통해 celery.py에서 별도로 include 리스트를 관리하거나 복잡한 로직을 넣을 필요 없이,
# autodiscover_tasks가 이 패키지를 로드할 때 모든 태스크가 자동으로 등록됩니다.

package_dir = Path(__file__).resolve().parent

__all__ = []

for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
    # 하위 모듈 임포트 (예: backend.celery_app.tasks.reclassification)
    module = importlib.import_module(f"{__name__}.{module_name}")
    __all__.append(module_name)

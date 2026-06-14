# tests/test_conflict_cases_scenarios/__init__.py

"""테스트 시나리오 기본 설정"""

import sys
from pathlib import Path

# 프로젝트 루트를 자동으로 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

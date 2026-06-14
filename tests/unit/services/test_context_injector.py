# tests/test_context_injector.py
# 개선된 E2E 테스트 코드 - 결과를 tests/outputs/에 저장
import json
import os
import sys
from datetime import datetime
from io import BytesIO
from multiprocessing import process
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 경로 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 출력 디렉토리 생성
OUTPUT_DIR = project_root / "tests" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

from backend.classifier.context_injector import ContextInjector


def test_context_injector():
    print("\n" + "=" * 50)
    print("🧪 ContextInjector 결과 구조 검증 테스트 시작")
    print("=" * 50)

    injector = ContextInjector()

    # ----------------------------------------------------
    # 테스트 케이스 1: 초기화 필수 키 및 ContextInjector 로직 테스트
    # ----------------------------------------------------
    context_data_1 = {
        "name": "프로젝트 관리",
        "description": "팀 리드 및 일정 관리",
        "keywords": "회의",
        "occupation": "개발자",
        "areas": [
            "코드 품질 관리",
            "기술 학습 및 연구",
            "팀 협업",
            "프로젝트 일정 관리",
            "시스템 아키텍처",
        ],
        "interests": "일정 관리",
        "recent_categories": "P",
        "total_classifications": "P",
        "last_updated": "2025-10-10",
    }

    processed_data1 = injector._format_context(context_data_1)

    processed_data1

    print(type(processed_data1))
    print("\n[def _format_context() 검증 중]...")
    print(f"data/context/user_context_mapping.json의 구조를 그대로 입력함")


if __name__ == "__main__":
    test_context_injector

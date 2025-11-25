# tests/test_integration_onboarding_classification.py

import sys
from pathlib import Path

import io
import os
import uuid
import pytest
import requests

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

"""
온보딩 + 분류 통합 테스트

터미널에서 수동으로 했던 흐름을 그대로 pytest로 옮긴 버전:
  1) 온보딩 step1 → user_id 발급
  2) suggest-areas 호출
  3) save-context로 영역 저장
  4) status에서 온보딩 완료 상태 확인
  5) (파일 분류 대신) /api/health 와 /api/classify/file 엔드포인트가 정상 동작하는지만 검증

※ 실제 LangGraph 분류 내용까지 단정하지 않고,
   "엔드포인트가 살아 있고, 200 / 400 정도의 정상 응답이 온다" 수준으로만 본다.
"""

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def test_onboarding_to_classification_file_flow(client):
    """
    온보딩(step1 → suggest-areas → save-context → status) 후
    분류 관련 엔드포인트(/api/classify/file)가 정상 동작하는지까지 한 번에 검증.
    (TestClient 사용으로 서버 실행 불필요)
    """

    # 0. 서버 health 체크
    h = client.get("/health")
    assert h.status_code == 200, h.text
    health_data = h.json()
    assert health_data.get("status") == "healthy"
    assert "timestamp" in health_data
    assert health_data.get("version") == "4.0.0"

    # 1. 온보딩 Step 1: 직업 입력 → user_id 생성
    r1 = client.post(
        "/onboarding/step1",
        json={
            "name": "TestUser",
            "occupation": "Developer",
        },
    )
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert data1["status"] == "success"
    assert "user_id" in data1
    user_id = data1["user_id"]

    # 2. 온보딩 Step 2(옵션): GPT-4o 영역 추천
    r2 = client.get(
        "/onboarding/suggest-areas",
        params={
            "user_id": user_id,
            "occupation": "Developer",
        },
    )
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["status"] == "success"
    assert data2["user_id"] == user_id

    # 3. 온보딩 Step 3: 선택한 영역 저장 (/save-context)
    r3 = client.post(
        "/onboarding/save-context",
        json={
            "user_id": user_id,
            "selected_areas": ["Python", "AI"],
        },
    )
    assert r3.status_code == 200, r3.text
    data3 = r3.json()
    assert data3["status"] == "success"
    assert data3["user_id"] == user_id
    assert "selected_areas" in data3

    # 4. 온보딩 상태 확인
    r4 = client.get(f"/onboarding/status/{user_id}")
    assert r4.status_code == 200, r4.text
    data4 = r4.json()
    assert data4["status"] == "success"
    assert data4["user_id"] == user_id
    assert data4["is_completed"] is True
    assert "Python" in data4["areas"]

    # 5. 분류 엔드포인트 연동 테스트 (파일 업로드 기반)
    dummy_filename = f"test_{uuid.uuid4().hex[:8]}.txt"
    dummy_content = (
        "FlowNote 개발 TODO\n- 온보딩 통합 테스트\n- 분류 엔드포인트 연동 확인\n"
    )

    files = {
        "file": (
            dummy_filename,
            io.BytesIO(dummy_content.encode("utf-8")),
            "text/plain",
        )
    }

    r5 = client.post("/classifier/file", files=files)
    assert r5.status_code == 200, r5.text
    data5 = r5.json()

    assert "category" in data5
    assert "keyword_tags" in data5


"""test_result

pytest tests/test_integration_onboarding_classification.py -v

======================================================== test session starts =========================================================
platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
cachedir: .pytest_cache
rootdir: /Users/jay/ICT-projects/flownote-mvp
configfile: pytest.ini
plugins: anyio-4.11.0, langsmith-0.4.37, asyncio-1.3.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collected 1 item                                                                                                                     

tests/test_integration_onboarding_classification.py::test_onboarding_to_classification_file_flow PASSED                        [100%]

========================================================= 1 passed in 18.18s =========================================================

"""

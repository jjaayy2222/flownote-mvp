# tests/test_api_dashboard.py

"""API Dashboard Endpoints - Unit & Integration Tests"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 경로 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# FastAPI 테스트 클라이언트를 위한 더미 앱
from fastapi import FastAPI

from backend.api.endpoints.dashboard import router

# 테스트 앱 생성
app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestDashboardEndpoints:
    """Dashboard API 엔드포인트 테스트"""

    def test_status_endpoint(self):
        """GET /dashboard/status"""
        print("🧪 Testing: GET /dashboard/status")
        response = client.get("/dashboard/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"✅ Response: {data}")

    def test_metrics_endpoint(self):
        """GET /dashboard/metrics"""
        print("🧪 Testing: GET /dashboard/metrics")
        response = client.get("/dashboard/metrics")
        assert response.status_code == 200
        data = response.json()
        # MetadataAggregator 데이터 체크
        assert "file_statistics" in data or "total_files" in data
        print(f"✅ Response keys: {data.keys()}")

    def test_keywords_endpoint(self):
        """GET /dashboard/keywords?top_n=5"""
        print("🧪 Testing: GET /dashboard/keywords?top_n=5")
        response = client.get("/dashboard/keywords?top_n=5")
        assert response.status_code == 200
        data = response.json()
        assert "top_keywords" in data
        print(f"✅ Top keywords count: {len(data['top_keywords'])}")

    def test_keywords_with_custom_params(self):
        """GET /dashboard/keywords?top_n=20"""
        print("🧪 Testing: GET /dashboard/keywords?top_n=20")
        response = client.get("/dashboard/keywords?top_n=20")
        assert response.status_code == 200
        data = response.json()
        assert "top_keywords" in data
        print(f"✅ Response length: {len(data['top_keywords'])}")


# 테스트
if __name__ == "__main__":
    print("🚀 Running API Dashboard Tests\n")
    test = TestDashboardEndpoints()

    try:
        test.test_status_endpoint()
        print()
        test.test_metrics_endpoint()
        print()
        test.test_keywords_endpoint()
        print()
        test.test_keywords_with_custom_params()
        print("\n✅ All API tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")


"""test_result_1 - 직접 실행 = `python tests/test_api_dashboard.py`

    🚀 Running API Dashboard Tests

    🧪 Testing: GET /dashboard/status
    ✅ MetadataAggregator loaded successfully
    ✅ Response: {'status': 'ready', 'statistics': {'total_files': 9, 'total_searches': 0, 'by_type': {'text': 9}, 'by_category': {'Archives': 2, 'Areas': 3, 'Projects': 3}, 'top_keywords': ['PARA', 'Dashboard', '분류', 'LangChain', '메타데이터']}}

    🧪 Testing: GET /dashboard/metrics
    ✅ Response keys: dict_keys(['file_statistics', 'para_breakdown', 'keyword_categories'])

    🧪 Testing: GET /dashboard/keywords?top_n=5
    ✅ Top keywords count: 5

    🧪 Testing: GET /dashboard/keywords?top_n=20
    ✅ Response length: 5

    ✅ All API tests passed!

"""


"""test_result_2 - pytest로 실행 =`pytest tests/test_api_dashboard.py -v`

========================================================= test session starts ==========================================================
platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
cachedir: .pytest_cache
rootdir: /Users/jay/ICT-projects/flownote-mvp
plugins: anyio-4.11.0, langsmith-0.4.37
collected 4 items                                                                                                                      

tests/test_api_dashboard.py::TestDashboardEndpoints::test_status_endpoint PASSED                                                 [ 25%]
tests/test_api_dashboard.py::TestDashboardEndpoints::test_metrics_endpoint PASSED                                                [ 50%]
tests/test_api_dashboard.py::TestDashboardEndpoints::test_keywords_endpoint PASSED                                               [ 75%]
tests/test_api_dashboard.py::TestDashboardEndpoints::test_keywords_with_custom_params PASSED                                     [100%]

========================================================== 4 passed in 0.89s ===========================================================

"""


"""test_result_3 - 상세 출력 = `pytest tests/test_api_dashboard.py -v -s`

    ========================================================= test session starts ==========================================================
    platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/jay/ICT-projects/flownote-mvp
    plugins: anyio-4.11.0, langsmith-0.4.37
    collected 4 items                                                                                                                      

    tests/test_api_dashboard.py::TestDashboardEndpoints::test_status_endpoint 🧪 Testing: GET /dashboard/status
    ✅ MetadataAggregator loaded successfully
    ✅ Response: {'status': 'ready', 'statistics': {'total_files': 9, 'total_searches': 0, 'by_type': {'text': 9}, 'by_category': {'Archives': 2, 'Areas': 3, 'Projects': 3}, 'top_keywords': ['PARA', 'Dashboard', '분류', 'LangChain', '메타데이터']}}
    PASSED
    tests/test_api_dashboard.py::TestDashboardEndpoints::test_metrics_endpoint 🧪 Testing: GET /dashboard/metrics
    ✅ Response keys: dict_keys(['file_statistics', 'para_breakdown', 'keyword_categories'])
    PASSED
    tests/test_api_dashboard.py::TestDashboardEndpoints::test_keywords_endpoint 🧪 Testing: GET /dashboard/keywords?top_n=5
    ✅ Top keywords count: 5
    PASSED
    tests/test_api_dashboard.py::TestDashboardEndpoints::test_keywords_with_custom_params 🧪 Testing: GET /dashboard/keywords?top_n=20
    ✅ Response length: 5
    PASSED

    ========================================================== 4 passed in 0.34s ===========================================================

"""

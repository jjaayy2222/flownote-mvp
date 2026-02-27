# tests/unit/test_search_endpoint.py

"""
Step 6: /search/hybrid 엔드포인트 단위 테스트

HybridSearchService를 모킹하여 엔드포인트의 라우팅/검증/직렬화 로직만 검증합니다.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.hybrid_search_service import (
    HybridSearchService,
    get_hybrid_search_service,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 픽스처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


def _make_mock_result(
    content: str = "테스트 문서 내용",
    category: str = "Projects",
    score: float = 0.05,
) -> Dict[str, Any]:
    return {
        "content": content,
        "metadata": {"category": category, "source": "test.md"},
        "score": score,
    }


@pytest.fixture()
def mock_service() -> MagicMock:
    """HybridSearchService 모킹 픽스처."""
    svc = MagicMock(spec=HybridSearchService)
    svc.search.return_value = {
        "results": [_make_mock_result()],
        "applied_filter": {"category": "Projects"},
    }
    return svc


@pytest.fixture()
def client(mock_service: MagicMock) -> TestClient:
    """모킹된 서비스를 DI로 주입한 TestClient."""
    app.dependency_overrides[get_hybrid_search_service] = lambda: mock_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# POST /search/hybrid 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_hybrid_search_post_basic(client: TestClient, mock_service: MagicMock):
    """기본 POST 요청이 성공적으로 처리되어야 한다."""
    payload = {"query": "프로젝트 일정", "k": 3, "alpha": 0.5, "category": "Projects"}
    response = client.post("/search/hybrid", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["query"] == "프로젝트 일정"
    assert data["count"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["content"] == "테스트 문서 내용"
    assert data["alpha"] == 0.5


def test_hybrid_search_post_no_category(client: TestClient, mock_service: MagicMock):
    """category 없이 POST 요청도 성공해야 한다."""
    mock_service.search.return_value = {
        "results": [_make_mock_result()],
        "applied_filter": None,
    }
    payload = {"query": "파이썬 비동기"}
    response = client.post("/search/hybrid", json=payload)

    assert response.status_code == 200
    assert response.json()["applied_filter"] is None


def test_hybrid_search_post_empty_query_returns_422(client: TestClient):
    """빈 쿼리는 422 Unprocessable Entity를 반환해야 한다."""
    response = client.post("/search/hybrid", json={"query": ""})
    assert response.status_code == 422


def test_hybrid_search_post_alpha_out_of_range_returns_422(client: TestClient):
    """alpha가 [0, 1] 범위를 벗어나면 422를 반환해야 한다."""
    response = client.post("/search/hybrid", json={"query": "테스트", "alpha": 1.5})
    assert response.status_code == 422


def test_hybrid_search_post_k_out_of_range_returns_422(client: TestClient):
    """k가 1 미만이거나 50 초과이면 422를 반환해야 한다."""
    response = client.post("/search/hybrid", json={"query": "테스트", "k": 0})
    assert response.status_code == 422

    response = client.post("/search/hybrid", json={"query": "테스트", "k": 51})
    assert response.status_code == 422


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# GET /search/hybrid 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_hybrid_search_get_basic(client: TestClient, mock_service: MagicMock):
    """기본 GET 요청이 성공적으로 처리되어야 한다."""
    response = client.get("/search/hybrid?q=검색+테스트&k=5&category=Areas")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["query"] == "검색 테스트"
    assert data["count"] == 1


def test_hybrid_search_get_missing_query_returns_422(client: TestClient):
    """q 파라미터가 없으면 422를 반환해야 한다."""
    response = client.get("/search/hybrid")
    assert response.status_code == 422


def test_hybrid_search_get_invalid_category_propagates(
    client: TestClient, mock_service: MagicMock
):
    """서비스에서 ValueError 발생 시 422로 변환되어야 한다."""
    mock_service.search.side_effect = ValueError("지원하지 않는 카테고리: 'InvalidCat'")
    response = client.get("/search/hybrid?q=테스트&category=InvalidCat")
    assert response.status_code == 422


def test_hybrid_search_get_service_error_returns_500(
    client: TestClient, mock_service: MagicMock
):
    """서비스에서 예기치 않은 예외 발생 시 500을 반환해야 한다."""
    mock_service.search.side_effect = RuntimeError("Unexpected error")
    response = client.get("/search/hybrid?q=테스트")
    assert response.status_code == 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# HybridSearchService 단위 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestHybridSearchServiceBuildFilter:
    """HybridSearchService._build_metadata_filter 단위 검증."""

    def test_no_args_returns_none(self):
        result = HybridSearchService._build_metadata_filter(None, None)
        assert result is None

    def test_category_only(self):
        result = HybridSearchService._build_metadata_filter("Projects", None)
        assert result == {"category": "Projects"}

    def test_extra_filter_only(self):
        result = HybridSearchService._build_metadata_filter(None, {"source": "a.md"})
        assert result == {"source": "a.md"}

    def test_category_and_extra_filter_merged(self):
        result = HybridSearchService._build_metadata_filter("Areas", {"source": "b.md"})
        assert result == {"category": "Areas", "source": "b.md"}

    def test_invalid_category_raises_value_error(self):
        with pytest.raises(ValueError, match="지원하지 않는 카테고리"):
            HybridSearchService._build_metadata_filter("InvalidCat", None)

    def test_all_para_categories_accepted(self):
        from backend.api.models import PARA_CATEGORIES

        for cat in PARA_CATEGORIES:
            result = HybridSearchService._build_metadata_filter(cat, None)
            assert result == {"category": cat}

    def test_extra_filter_does_not_override_category(self):
        """extra_filter에 'category' 키가 있어도 명시적 category 인자로 덮어써야 한다."""
        result = HybridSearchService._build_metadata_filter(
            "Projects", {"category": "Areas", "source": "c.md"}
        )
        assert result["category"] == "Projects"
        assert result["source"] == "c.md"

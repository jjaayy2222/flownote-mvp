# tests/unit/test_search_endpoint.py

"""
Step 6: /search/hybrid 엔드포인트 단위 테스트 (리팩토링 반영)

1. 레거시 GET /search/ 엔드포인트 하위 호환성 테스트 추가
2. PARACategory Enum 및 HybridSearchResult DTO 반영
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.models import PARACategory, HybridSearchResponse
from backend.services.hybrid_search_service import (
    HybridSearchService,
    get_hybrid_search_service,
    HybridSearchResult,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 픽스처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


def _make_mock_doc(
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
    # DTO 객체를 반환하도록 설정
    svc.search.return_value = HybridSearchResult(
        results=[_make_mock_doc()],
        applied_filter={"category": "Projects"},
    )
    return svc


@pytest.fixture()
def client(mock_service: MagicMock) -> TestClient:
    """모킹된 서비스를 DI로 주입한 TestClient."""
    app.dependency_overrides[get_hybrid_search_service] = lambda: mock_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 레거시 /search/ 테스트 (하위 호환성)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_legacy_search_get_compatibility(client: TestClient):
    """레거시 GET /search/ 엔드포인트가 정상 작동하고 필수 필드를 포함해야 한다."""
    response = client.get("/search/?q=legacy-query")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "message" in data
    assert data["query"] == "legacy-query"
    assert data["results"] == []
    assert data["count"] == 0


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
    mock_service.search.return_value = HybridSearchResult(
        results=[_make_mock_doc()],
        applied_filter=None,
    )
    payload = {"query": "파이썬 비동기"}
    response = client.post("/search/hybrid", json=payload)

    assert response.status_code == 200
    assert response.json()["applied_filter"] is None


def test_hybrid_search_post_invalid_enum_value(client: TestClient):
    """잘못된 카테고리 Enum 값 요청 시 422 에러가 발생해야 한다."""
    response = client.post(
        "/search/hybrid", json={"query": "테스트", "category": "Invalid"}
    )
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# HybridSearchService 단위 테스트 (빌드 필터)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestHybridSearchServiceBuildFilter:
    """HybridSearchService._build_metadata_filter 단위 검증."""

    def test_no_args_returns_none(self):
        result = HybridSearchService._build_metadata_filter(None, None)
        assert result is None

    def test_category_enum_conversion(self):
        """Enum이 문자열 값으로 올바르게 변환되는지 확인."""
        result = HybridSearchService._build_metadata_filter(PARACategory.PROJECTS, None)
        assert result == {"category": "Projects"}

    def test_category_and_extra_filter_merged(self):
        result = HybridSearchService._build_metadata_filter(
            PARACategory.AREAS, {"source": "b.md"}
        )
        assert result == {"category": "Areas", "source": "b.md"}

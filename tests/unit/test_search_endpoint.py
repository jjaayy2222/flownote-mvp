# tests/unit/test_search_endpoint.py

"""
Step 6: /search/hybrid 엔드포인트 단위 테스트 (리팩토링 최종 반영)

리뷰 피드백 반영:
1. 의존성 주입(DI)을 활용하여 Mock 리트리버를 서비스에 직접 주입 (patch 의존성 제거)
2. Fixture를 활용하여 테스트 중복 코드 제거 및 유지보수성 향상
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.models import PARACategory
from backend.services.hybrid_search_service import (
    HybridSearchService,
    get_hybrid_search_service,
    HybridSearchResult,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 픽스처 (Fixtures)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


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


@pytest.fixture
def mock_retrievers():
    """리트리버 Mock 객체 쌍을 생성하는 Fixture."""
    return (MagicMock(name="FAISS"), MagicMock(name="BM25"))


@pytest.fixture
def hybrid_service(mock_retrievers):
    """의존성이 주입된 HybridSearchService 인스턴스를 생성하는 Fixture."""
    faiss, bm25 = mock_retrievers
    # 실제 FAISSRetriever/BM25Retriever 클래스 대신 Mock을 주입 (DI)
    svc = HybridSearchService(faiss_retriever=faiss, bm25_retriever=bm25)
    # searcher.search 메서드를 기본적으로 가짜 결과 반환하도록 설정
    svc.searcher.search = MagicMock(return_value=[_make_mock_doc()])
    return svc


@pytest.fixture
def client(hybrid_service):
    """모킹된 서비스를 DI로 주입한 TestClient."""
    app.dependency_overrides[get_hybrid_search_service] = lambda: hybrid_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 엔드포인트 테스트 (API Routing & Schema)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def test_legacy_search_get_compatibility(client: TestClient):
    """레거시 GET /search/ 엔드포인트의 하위 호환성(필드 구성)을 전체 검증."""
    response = client.get("/search/?q=legacy-query")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "message" in data  # 응답 메시지 존재 여부 확인
    assert data["query"] == "legacy-query"
    assert data["results"] == []
    assert data["count"] == 0  # 검색 결과 개수 필드 복구


def test_hybrid_search_post_basic(client: TestClient, hybrid_service):
    """기본 POST 요청 및 DTO 변환 확인."""
    payload = {"query": "프로젝트", "k": 3, "category": "Projects"}
    response = client.post("/search/hybrid", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["results"]) == 1
    assert data["results"][0]["content"] == "테스트 문서 내용"


def test_hybrid_search_get_basic(client: TestClient):
    """기본 GET 요청 확인."""
    response = client.get("/search/hybrid?q=검색&category=Areas")
    assert response.status_code == 200
    assert response.json()["query"] == "검색"


def test_hybrid_search_invalid_category(client: TestClient):
    """잘못된 카테고리 입력 시 Schema 에러 확인."""
    response = client.post("/search/hybrid", json={"query": "x", "category": "Invalid"})
    assert response.status_code == 422


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 서비스 레이어 단위 테스트 (Validation & Filter)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestHybridSearchServiceLogic:
    """HybridSearchService 내부 로직 단위 검증."""

    def test_search_alpha_out_of_range(self, hybrid_service):
        """alpha 범위 검증."""
        with pytest.raises(ValueError, match="alpha must be between 0.0 and 1.0"):
            hybrid_service.search(query="t", alpha=1.1)

    def test_search_k_min_validation(self, hybrid_service):
        """k 최소값 검증."""
        with pytest.raises(ValueError, match="k must be greater than or equal to 1"):
            hybrid_service.search(query="t", k=0)

    def test_search_boundary_accepts_valid_values(self, hybrid_service):
        """파라미터 경계값 허용 확인 (DI 기반 테스트)."""
        # DI 덕분에 patch 없이 직접 mock 호출 여부 확인 가능
        hybrid_service.search(query="test", k=1, alpha=0.0)
        hybrid_service.search(query="test", k=50, alpha=1.0)
        assert hybrid_service.searcher.search.call_count == 2

    def test_build_filter_category_conflict(self):
        """카테고리 충돌 방지 로직 확인."""
        with pytest.raises(ValueError, match="Category conflict"):
            HybridSearchService._build_metadata_filter(
                PARACategory.PROJECTS, {"category": "Areas"}
            )

    def test_build_filter_success(self):
        """필터 빌드 성공 케이스 확인."""
        result = HybridSearchService._build_metadata_filter(
            PARACategory.RESOURCES, {"other": "val"}
        )
        assert result == {"category": "Resources", "other": "val"}

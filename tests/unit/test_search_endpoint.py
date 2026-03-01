# tests/unit/test_search_endpoint.py

"""
Step 6: /search/hybrid 엔드포인트 단위 테스트 (리팩토링 최종 반영)

리뷰 피드백 반영:
1. 클래스 상수(DEFAULT_RRF_K 등)를 활용한 기본값 검증
2. 생성자 호출 경로 전수 테스트 (기본, 순수 키워드, DI 사용 등)
3. 외부 관찰 가능한 동작(searcher.rrf_k 등) 검증 강화
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
    from backend.faiss_search import FAISSRetriever
    from backend.bm25_search import BM25Retriever

    faiss = MagicMock(spec=FAISSRetriever)
    bm25 = MagicMock(spec=BM25Retriever)

    # HybridSearchService가 기대하는 기본 차원을 설정하여 AttributeError 방지
    faiss.dimension = HybridSearchService.DEFAULT_FAISS_DIMENSION

    faiss.search.return_value = []
    bm25.search.return_value = []
    return (faiss, bm25)


@pytest.fixture
def hybrid_service(mock_retrievers):
    """의존성이 주입된 HybridSearchService 인스턴스를 생성하는 Fixture."""
    faiss, bm25 = mock_retrievers
    svc = HybridSearchService(faiss_retriever=faiss, bm25_retriever=bm25)
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
    assert "message" in data
    assert data["query"] == "legacy-query"
    assert data["results"] == []
    assert data["count"] == 0


def test_hybrid_search_post_basic(client: TestClient, hybrid_service):
    """기본 POST 요청 및 DTO 변환 확인."""
    payload = {"query": "프로젝트", "k": 3, "category": "Projects"}
    response = client.post("/search/hybrid", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["results"]) == 1
    assert data["results"][0]["content"] == "테스트 문서 내용"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 생성자 초기화 테스트 (Initialization Paths)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestHybridSearchServiceInitialization:
    """하위 호환성을 보장하는 지능형 생성자 초기화 검증."""

    def test_init_with_no_arguments(self):
        """인수가 없는 기본 생성자 호출 시 기본값과 DI 플래그를 확인."""
        svc = HybridSearchService()
        assert svc.is_di is False
        assert svc.searcher.rrf_k == HybridSearchService.DEFAULT_RRF_K
        assert (
            svc.faiss_retriever.dimension == HybridSearchService.DEFAULT_FAISS_DIMENSION
        )
        assert svc.faiss_retriever is not None
        assert svc.bm25_retriever is not None

    def test_init_with_positional_rrf_k(self):
        """기본 순서 (rrf_k, dim) 위치 인수 호출 확인."""
        svc = HybridSearchService(10, 2048)
        assert svc.is_di is False
        assert svc.searcher.rrf_k == 10
        assert svc.faiss_retriever.dimension == 2048

    def test_init_with_keyword_rrf_k_and_dimension(self):
        """키워드 인수만 사용한 rrf_k, dim 초기화 및 DI 플래그 확인."""
        svc = HybridSearchService(rrf_k=30, faiss_dimension=1024)
        assert svc.is_di is False
        assert svc.searcher.rrf_k == 30
        assert svc.faiss_retriever.dimension == 1024

    def test_init_with_keyword_retrievers_di_enabled(self, mock_retrievers):
        """키워드 기반 검색기 주입 시 DI 플래그 및 주입 객체 확인."""
        faiss, bm25 = mock_retrievers
        svc = HybridSearchService(faiss_retriever=faiss, bm25_retriever=bm25)
        assert svc.is_di is True
        assert svc.faiss_retriever is faiss
        assert svc.bm25_retriever is bm25

    def test_init_with_positional_retrievers(self, mock_retrievers):
        """과거/대안 순서 (retriever1, retriever2) 위치 인수 호출 확인."""
        faiss, bm25 = mock_retrievers
        svc = HybridSearchService(faiss, bm25)
        assert svc.is_di is True
        assert svc.faiss_retriever is faiss
        assert svc.bm25_retriever is bm25

    def test_init_with_mixed_args_full_case_b(self, mock_retrievers):
        """Case B (ret1, ret2, rrf_k, dim) 위치 인수 호출 확인."""
        faiss, bm25 = mock_retrievers
        svc = HybridSearchService(faiss, bm25, 45, 1024)
        assert svc.faiss_retriever is faiss
        assert svc.bm25_retriever is bm25
        # 내부에 전달된 파라미터 해석 결과가 올바른지 확인
        assert svc._resolved_params["rrf_k"] == 45
        assert svc._resolved_params["faiss_dim"] == 1024
        assert svc.searcher.rrf_k == 45

    def test_init_keyword_precedence(self):
        """위치 인수보다 키워드 인수가 우선하는지 확인."""
        # 위치로는 10을 줬지만, 키워드로 99를 준 경우 99가 유지되어야 함 (Keyword Wins)
        svc = HybridSearchService(10, rrf_k=99)
        assert svc.searcher.rrf_k == 99

    def test_init_with_too_many_positional_args(self):
        """정의된 4개를 초과하는 위치 인수가 들어올 경우 TypeError 발생 확인."""
        with pytest.raises(TypeError, match="takes up to 4 positional arguments"):
            # 5개의 인자 전달
            HybridSearchService(60, 1536, None, None, "extra")

    def test_init_with_invalid_positional_type_logs_warning(self, caplog):
        """위치 인수의 타입이 예상과 다를 경우 경고 로그가 남는지 확인."""
        import logging

        with caplog.at_level(logging.WARNING):
            # i=0에 int나 Retriever가 아닌 문자열 전달
            svc = HybridSearchService("invalid-type")
            # 해석은 실패하지만 생성은 되어야 함 (기본값 사용)
            assert svc.searcher.rrf_k == HybridSearchService.DEFAULT_RRF_K
            assert "did not match any expected types" in caplog.text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 도메인 로직 테스트 (Logic & Validation)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestHybridSearchServiceLogic:
    """HybridSearchService 내부 로직 단위 검증."""

    @pytest.mark.asyncio
    async def test_search_alpha_out_of_range(self, hybrid_service):
        """alpha 범위 검증."""
        with pytest.raises(ValueError, match="alpha must be between 0.0 and 1.0"):
            await hybrid_service.search(query="t", alpha=1.1)

    @pytest.mark.asyncio
    async def test_search_k_min_validation(self, hybrid_service):
        """k 최소값 검증."""
        with pytest.raises(ValueError, match="k must be greater than or equal to 1"):
            await hybrid_service.search(query="t", k=0)

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

    @pytest.mark.asyncio
    async def test_search_expansion_factor_applied_only_with_filter(
        self, mock_retrievers
    ):
        """메타데이터 필터가 있을 때만 expansion_factor가 적용되는지 확인."""
        faiss, bm25 = mock_retrievers
        # searcher.search를 모킹하지 않은 순수 서비스 인스턴스 생성
        svc = HybridSearchService(faiss_retriever=faiss, bm25_retriever=bm25)

        k = 5
        factor = 3

        # Case 1: No filter (service call without category/filter)
        await svc.search("query", k=k, filter_expansion_factor=factor)
        # Service internal build_filter returns None if no category/extra_filter
        faiss.search.assert_called_with("query", k=k, metadata_filter=None)
        bm25.search.assert_called_with("query", k=k, metadata_filter=None)

        # Case 2: With filter (service call with category)
        await svc.search(
            "query", k=k, filter_expansion_factor=factor, category=PARACategory.PROJECTS
        )
        expected_filter = {"category": "Projects"}
        faiss.search.assert_called_with(
            "query", k=k * factor, metadata_filter=expected_filter
        )
        bm25.search.assert_called_with(
            "query", k=k * factor, metadata_filter=expected_filter
        )

    @pytest.mark.asyncio
    async def test_search_expansion_factor_validation_delegation(self, mock_retrievers):
        """expansion_factor 검증이 searcher로 위임되어 작동하는지 확인."""
        faiss, bm25 = mock_retrievers
        svc = HybridSearchService(faiss_retriever=faiss, bm25_retriever=bm25)

        with pytest.raises(
            ValueError, match="filter_expansion_factor must be at least 1"
        ):
            await svc.search("query", filter_expansion_factor=0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SearchCacheService 캐시 키 로직 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestSearchCacheServiceKeyGeneration:
    """SearchCacheService.make_cache_key 로직 단위 검증.

    [Review 반영] 테스트가 내부 구현(_generate_key)에 결합되지 않도록
    공개 헬퍼(make_cache_key)를 사용합니다.
    """

    def setup_method(self):
        from backend.services.search_cache_service import SearchCacheService

        self.svc = SearchCacheService()

    def test_different_expansion_factor_produces_different_keys(self):
        """filter_expansion_factor가 다르면 캐시 키가 달라야 한다.

        [Review 반영] filter_expansion_factor가 결과에 영향을 미치므로
        캐시 키에 포함하지 않으면 잘못된 캐시 히트가 발생한다.
        """
        key1 = self.svc.make_cache_key("query", 5, 0.5, None, 2)
        key2 = self.svc.make_cache_key("query", 5, 0.5, None, 10)
        assert (
            key1 != key2
        ), "expansion_factor가 다르면 다른 캐시 키가 생성되어야 합니다"

    def test_same_params_produces_same_key(self):
        """동일한 파라미터는 항상 같은 캐시 키를 생성해야 한다."""
        key1 = self.svc.make_cache_key("query", 5, 0.5, {"category": "Projects"}, 2)
        key2 = self.svc.make_cache_key("query", 5, 0.5, {"category": "Projects"}, 2)
        assert key1 == key2

    def test_alpha_float_normalization_same_key(self):
        """부동소수점 표현 오차가 있는 alpha는 정규화 후 동일한 키를 생성해야 한다.

        [Review 반영] IEEE 754 부동소수점 오류로 인한 캐시 미스 방지.
        0.1 + 0.2 == 0.30000000000000004 이므로 round() 정규화가 필요하다.
        """
        alpha_exact = 0.5
        # 극미한 부동소수점 오차 (round(..., 6) 이내)
        alpha_near = 0.5000001
        key_exact = self.svc.make_cache_key("query", 5, alpha_exact, None, 2)
        key_near = self.svc.make_cache_key("query", 5, alpha_near, None, 2)
        # round(..., 6) → 둘 다 0.5로 정규화되어 같은 키
        assert key_exact == key_near

    def test_alpha_float_significantly_different_produces_different_key(self):
        """의미 있는 차이의 alpha는 다른 캐시 키를 생성해야 한다."""
        key1 = self.svc.make_cache_key("query", 5, 0.3, None, 2)
        key2 = self.svc.make_cache_key("query", 5, 0.7, None, 2)
        assert key1 != key2

    def test_different_filter_produces_different_keys(self):
        """필터가 다르면 캐시 키가 달라야 한다."""
        key1 = self.svc.make_cache_key("query", 5, 0.5, {"category": "Projects"}, 2)
        key2 = self.svc.make_cache_key("query", 5, 0.5, {"category": "Areas"}, 2)
        assert key1 != key2

    def test_none_filter_and_empty_filter_behavior(self):
        """None 필터와 {} 필터의 키 분리 확인.

        [Review 반영] "필터 없음(None)"과 "빈 필터({})"는 의미가 다를 수 있으므로
        미래 호환성을 위해 캐시 키에서 이를 명확히 분리하여 인코딩합니다.
        """
        key_none = self.svc.make_cache_key("query", 5, 0.5, None, 2)
        key_empty = self.svc.make_cache_key("query", 5, 0.5, {}, 2)
        # 명시적으로 다른 키가 생성되어야 함
        assert key_none != key_empty


class TestLoadIndicesReturnValue:
    """load_indices 반환값 및 예외 처리 검증."""

    def test_load_indices_returns_false_when_no_files(self, mock_retrievers):
        """인덱스 파일이 없을 때 load_indices는 False를 반환해야 한다."""
        from unittest.mock import patch

        faiss, bm25 = mock_retrievers
        svc = HybridSearchService(faiss_retriever=faiss, bm25_retriever=bm25)

        faiss.load.side_effect = FileNotFoundError("no index")
        result = svc.load_indices()
        assert result is False

    def test_load_indices_returns_false_on_deserialization_error(self, mock_retrievers):
        """손상된 인덱스 파일(역직렬화 오류) 시 load_indices는 False를 반환해야 한다."""
        faiss, bm25 = mock_retrievers
        svc = HybridSearchService(faiss_retriever=faiss, bm25_retriever=bm25)

        faiss.load.side_effect = Exception("UnpicklingError")
        result = svc.load_indices()
        assert result is False

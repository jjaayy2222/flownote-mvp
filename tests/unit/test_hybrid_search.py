import pytest
from typing import List, Dict, Any
from backend.hybrid_search import HybridSearcher


class DummyRetriever:
    """HybridSearcher 파라미터 검증용 더미 리트리버.
    HybridSearcher가 내부적으로 호출하는 search 인터페이스에만 의존하도록 구현합니다.
    """

    def __init__(self, name: str):
        self.name = name
        self.last_k = None
        self.last_query = None

    def search(self, query: str, k: int) -> List[Dict[str, Any]]:
        self.last_query = query
        self.last_k = k
        # HybridSearcher가 기대하는 최소 필드(content, metadata, score)를 맞춰줍니다.
        return [
            {
                "content": f"{self.name}-doc-{i}",
                "metadata": {"source": self.name, "id": f"{self.name}_{i}"},
                "score": 1.0 / (i + 1),
            }
            for i in range(k)
        ]


@pytest.fixture
def hybrid_searcher():
    faiss_retriever = DummyRetriever("faiss")
    bm25_retriever = DummyRetriever("bm25")
    return (
        HybridSearcher(faiss_retriever, bm25_retriever),
        faiss_retriever,
        bm25_retriever,
    )


def test_hybrid_searcher_rrf_k_validation_with_zero_or_negative(hybrid_searcher):
    """HybridSearcher(rrf_k=0 또는 음수)에서 ValueError가 발생하는지 검증."""
    _, faiss, bm25 = hybrid_searcher

    # rrf_k = 0
    with pytest.raises(ValueError, match="rrf_k must be positive"):
        HybridSearcher(faiss, bm25, rrf_k=0)

    # rrf_k < 0
    with pytest.raises(ValueError, match="rrf_k must be positive"):
        HybridSearcher(faiss, bm25, rrf_k=-10)


def test_hybrid_searcher_alpha_out_of_range_raises(hybrid_searcher):
    """alpha가 [0, 1] 범위를 벗어나면 ValueError가 발생하는지 검증."""
    searcher, _, _ = hybrid_searcher

    # alpha < 0
    with pytest.raises(ValueError, match="alpha must be between 0 and 1"):
        searcher.search("test", k=3, alpha=-0.1)

    # alpha > 1
    with pytest.raises(ValueError, match="alpha must be between 0 and 1"):
        searcher.search("test", k=3, alpha=1.1)


def test_hybrid_searcher_alpha_boundary_values_allowed(hybrid_searcher):
    """alpha=0 및 alpha=1 경계값은 허용되어 정상 검색 결과를 반환해야 합니다."""
    searcher, _, _ = hybrid_searcher

    # alpha = 0
    results_alpha_0 = searcher.search("test", k=3, alpha=0.0)
    assert isinstance(results_alpha_0, list)
    assert len(results_alpha_0) > 0

    # alpha = 1
    results_alpha_1 = searcher.search("test", k=3, alpha=1.0)
    assert isinstance(results_alpha_1, list)
    assert len(results_alpha_1) > 0


def test_hybrid_searcher_k_zero_or_negative_returns_empty_or_raises(hybrid_searcher):
    """search(..., k=0 또는 k<0)에 대한 거동 검증."""
    searcher, _, _ = hybrid_searcher

    # k = 0 -> 빈 리스트 반환
    results_k_zero = searcher.search("test", k=0)
    assert results_k_zero == []

    # k < 0 -> ValueError (프로그램 오류 방지)
    with pytest.raises(ValueError, match="k must be non-negative"):
        searcher.search("test", k=-1)


def test_hybrid_searcher_individual_k_negative_raises(hybrid_searcher):
    """faiss_k 또는 bm25_k가 음수일 때 에러 발생 검증."""
    searcher, _, _ = hybrid_searcher

    with pytest.raises(ValueError, match="faiss_k must be non-negative"):
        searcher.search("test", k=3, faiss_k=-1)

    with pytest.raises(ValueError, match="bm25_k must be non-negative"):
        searcher.search("test", k=3, bm25_k=-1)


def test_hybrid_searcher_default_faiss_k_and_bm25_k_are_2x_k(hybrid_searcher):
    """faiss_k=None, bm25_k=None일 때 기본값이 k * 2로 전달되는지 검증."""
    searcher, faiss, bm25 = hybrid_searcher

    k = 3
    _ = searcher.search("test", k=k, faiss_k=None, bm25_k=None)

    assert faiss.last_k == k * 2
    assert bm25.last_k == k * 2


def test_hybrid_searcher_explicit_faiss_k_and_bm25_k_zero_are_used_as_is(
    hybrid_searcher,
):
    """faiss_k=0, bm25_k=0으로 명시했을 때 해당 값이 그대로 전달되는지 검증."""
    searcher, faiss, bm25 = hybrid_searcher

    _ = searcher.search("test", k=3, faiss_k=0, bm25_k=0)

    assert faiss.last_k == 0
    assert bm25.last_k == 0


def test_hybrid_searcher_rrf_scoring_logic():
    """RRF 점수 합산 및 정렬 로직 검증."""
    faiss = DummyRetriever("faiss")
    bm25 = DummyRetriever("bm25")
    searcher = HybridSearcher(faiss, bm25, rrf_k=60)

    # 수동 결과 설정
    # 문서 A는 FAISS 1위, BM25 없음
    # 문서 B는 FAISS 2위, BM25 1위
    faiss.search = lambda q, k: [
        {"content": "DocA", "metadata": {"id": "A"}},  # rank 1
        {"content": "DocB", "metadata": {"id": "B"}},  # rank 2
    ]
    bm25.search = lambda q, k: [
        {"content": "DocB", "metadata": {"id": "B"}},  # rank 1
        {"content": "DocC", "metadata": {"id": "C"}},  # rank 2
    ]

    results = searcher.search("test", k=3, alpha=0.5)

    # B는 두 엔진 상위권이므로 1위여야 함
    # Score B = 0.5 * (1/(60+2)) + 0.5 * (1/(60+1))
    # Score A = 0.5 * (1/(60+1))
    # Score C = 0.5 * (1/(60+2))
    assert results[0]["content"] == "DocB"
    assert results[1]["content"] == "DocA"
    assert results[2]["content"] == "DocC"


def test_one_engine_empty_results():
    """한쪽 엔진이 빈 결과를 반환해도 정상 동작하는지 검증."""
    faiss = DummyRetriever("faiss")
    bm25 = DummyRetriever("bm25")
    searcher = HybridSearcher(faiss, bm25)

    faiss.search = lambda q, k: [{"content": "DocA", "metadata": {"id": "A"}}]
    bm25.search = lambda q, k: []

    results = searcher.search("test", k=3)
    assert len(results) == 1
    assert results[0]["content"] == "DocA"

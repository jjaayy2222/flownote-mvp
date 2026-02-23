import pytest
import uuid
from typing import List, Dict, Any, Optional, Union, Hashable
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


class StaticRetriever:
    """고정된 검색 결과를 반환하는 리트리버 (테스트용)."""

    def __init__(self, results: List[Dict[str, Any]]):
        self._results = results
        self.last_query = None
        self.last_k = None

    def search(self, query: str, k: int) -> List[Dict[str, Any]]:
        self.last_query = query
        self.last_k = k
        return self._results[:k]


def _make_doc(
    content: str, doc_id: Optional[Hashable] = None, **metadata_overrides: Any
) -> Dict[str, Any]:
    """
    테스트용 문서 객체 생성 헬퍼 (ID 선택 가능).
    falsy한 ID("", 0, 0.0 등)가 누락되지 않도록 is not None으로 체크하며,
    Hashable 타입을 지원하여 미래의 다양한 ID 형식(UUID 등)에 대응합니다.
    """
    metadata = {}
    if doc_id is not None:
        metadata["id"] = doc_id
    metadata.update(metadata_overrides)
    return {"content": content, "metadata": metadata, "score": 1.0}


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
        {"content": "DocA", "metadata": {"id": "A"}, "score": 0.9},  # rank 1
        {"content": "DocB", "metadata": {"id": "B"}, "score": 0.8},  # rank 2
    ]
    bm25.search = lambda q, k: [
        {"content": "DocB", "metadata": {"id": "B"}, "score": 20.0},  # rank 1
        {"content": "DocC", "metadata": {"id": "C"}, "score": 15.0},  # rank 2
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

    faiss.search = lambda q, k: [
        {"content": "DocA", "metadata": {"id": "A"}, "score": 1.0}
    ]
    bm25.search = lambda q, k: []

    results = searcher.search("test", k=3)
    assert len(results) == 1
    assert results[0]["content"] == "DocA"


def test_hybrid_searcher_deduplicates_hash_key_when_id_missing():
    """
    metadata['id']가 없을 때 (content, source, chunk_index) 해시를 통한 중복 제거 검증.
    내용(content)이 같더라도 메타데이터가 다르면 별개 문서로 취급되어야 함을 확인합니다.
    """
    shared_content = "same content for all docs"
    shared_source = "shared-source"
    shared_chunk_idx = 0

    # 1. 병합되어야 하는 쌍 (내용, 출처, 인덱스 모두 동일)
    shared_doc_faiss = _make_doc(
        shared_content, source=shared_source, chunk_index=shared_chunk_idx
    )
    shared_doc_bm25 = _make_doc(
        shared_content, source=shared_source, chunk_index=shared_chunk_idx
    )

    # 2. 병합되지 않아야 하는 쌍 (내용은 같으나 출처/인덱스가 다름 -> 서로 다른 논리적 문서)
    variant_doc_faiss = _make_doc(shared_content, source="source-faiss", chunk_index=10)
    variant_doc_bm25 = _make_doc(shared_content, source="source-bm25", chunk_index=20)

    faiss_retriever = StaticRetriever([shared_doc_faiss, variant_doc_faiss])
    bm25_retriever = StaticRetriever([shared_doc_bm25, variant_doc_bm25])

    searcher = HybridSearcher(faiss_retriever, bm25_retriever)

    results = searcher.search("query", k=10)

    # shared_doc 1개(병합) + variant 2개(분리) = 총 3개 결과 기대
    assert len(results) == 3

    # shared_doc 병합 여부 확인 (특정 출처/인덱스 조합이 하나만 존재하는지)
    shared_results = [
        r
        for r in results
        if r["metadata"].get("source") == shared_source
        and r["metadata"].get("chunk_index") == shared_chunk_idx
    ]
    assert len(shared_results) == 1

    # variant_doc들이 분리되어 존재하는지 확인
    variant_sources = {r["metadata"].get("source") for r in results}
    assert "source-faiss" in variant_sources
    assert "source-bm25" in variant_sources


def test_hybrid_searcher_deduplicates_partial_metadata_hash():
    """
    메타데이터(source, chunk_index)가 일부 누락되었을 때의 해시 기반 중복 제거 검증.
    """
    shared_content = "partial metadata content"

    # 1. source만 있고 chunk_index가 없는 경우
    doc_a = _make_doc(shared_content, source="only-source")
    doc_b = _make_doc(shared_content, source="only-source")

    # 2. chunk_index만 있고 source가 없는 경우
    doc_c = _make_doc("other content", chunk_index=99)
    doc_d = _make_doc("other content", chunk_index=99)

    faiss_retriever = StaticRetriever([doc_a, doc_c])
    bm25_retriever = StaticRetriever([doc_b, doc_d])

    searcher = HybridSearcher(faiss_retriever, bm25_retriever)
    results = searcher.search("query", k=10)

    # doc_a/b 병합, doc_c/d 병합 -> 총 2개 결과 기대
    assert len(results) == 2

    # 각 내용별로 결과가 하나씩만 있는지 확인
    contents = [r["content"] for r in results]
    assert contents.count(shared_content) == 1
    assert contents.count("other content") == 1


def test_hybrid_searcher_falsy_id_preservation():
    """
    ID가 ""(str)와 0(int)과 같은 falsy 값들이 개별적으로 잘 보존되는지 검증.
    (참고: "0"(str)과 0(int)은 동일 키로 취급되어 병합되므로 여기선 충돌하지 않는 조합 확인)
    """
    doc_int_zero = _make_doc("content int 0", doc_id=0)
    doc_float_zero = _make_doc("content float 0.0", doc_id=0.0)
    doc_empty = _make_doc("content empty", doc_id="")

    faiss_retriever = StaticRetriever([doc_int_zero, doc_float_zero, doc_empty])
    bm25_retriever = StaticRetriever([])

    searcher = HybridSearcher(faiss_retriever, bm25_retriever)
    results = searcher.search("query", k=10)

    # 0(int), 0.0(float), ""(str) ID를 가진 문서가 각각 타입까지 정확히 보존되어야 함
    # (Python에서 0 == 0.0 이므로 값만 체크하면 교차 검증이 안 됨)
    id_and_types = [
        (r["metadata"].get("id"), type(r["metadata"].get("id"))) for r in results
    ]
    assert (0, int) in id_and_types
    assert (0.0, float) in id_and_types
    assert ("", str) in id_and_types


@pytest.mark.parametrize(
    "faiss_id, bm25_id",
    [
        ("0", 0),  # FAISS='0', BM25=0
        (0, "0"),  # FAISS=0, BM25='0' (역순 조합)
    ],
)
def test_hybrid_searcher_numeric_and_string_zero_id_merging(faiss_id, bm25_id):
    """
    동일 문서에 대해 리트리버들이 서로 다른 타입(문자열 '0' vs 숫자 0)의
    논리적 동일 ID를 반환할 때, 중복 없이 하나로 병합되는지 검증합니다.

    두 리트리버(FAISS/BM25)에 할당되는 ID 조합을 파라미터로 주어,
    리트리버 순서와 무관하게 일관된 중복 제거 결과가 산출되는지 확인합니다.
    """
    shared_content = "same content zero id"
    doc_a = _make_doc(shared_content, doc_id=faiss_id)
    doc_b = _make_doc(shared_content, doc_id=bm25_id)

    faiss_retriever = StaticRetriever([doc_a])
    bm25_retriever = StaticRetriever([doc_b])

    searcher = HybridSearcher(faiss_retriever, bm25_retriever)
    results = searcher.search("query", k=10)

    # 논리적으로 동일한 ID이므로 리트리버 순서와 무관하게 1개로 병합되어야 함
    assert len(results) == 1
    # 병합된 문서의 ID 값은 입력된 ID 중 하나와 논리적으로 동등(문자열 표현 일치)해야 함
    merged_id = results[0]["metadata"]["id"]
    assert str(merged_id) == str(faiss_id)


def test_hybrid_searcher_uuid_id_preservation():
    """
    _make_doc 및 HybridSearcher가 str/int 외의 Hashable 타입(예: UUID)을
    정상적으로 지원하고 보존하는지 검증.
    """
    shared_content = "uuid content"
    unique_id = uuid.uuid4()

    doc = _make_doc(shared_content, doc_id=unique_id)

    faiss_retriever = StaticRetriever([doc])
    bm25_retriever = StaticRetriever([])

    searcher = HybridSearcher(faiss_retriever, bm25_retriever)
    results = searcher.search("query", k=10)

    # UUID 객체가 그대로 메타데이터에 보존되어야 함
    assert results[0]["metadata"]["id"] == unique_id
    assert isinstance(results[0]["metadata"]["id"], uuid.UUID)


def test_hybrid_searcher_deduplicates_same_metadata_id():
    """동일한 metadata['id']를 가지는 문서 중복 제거 검증."""
    shared_doc_faiss = _make_doc("shared content", "doc-1", source="faiss")
    shared_doc_bm25 = _make_doc("shared content", "doc-1", source="bm25")

    faiss_only_doc = _make_doc("faiss only", "doc-2", source="faiss")
    bm25_only_doc = _make_doc("bm25 only", "doc-3", source="bm25")

    faiss_retriever = StaticRetriever([shared_doc_faiss, faiss_only_doc])
    bm25_retriever = StaticRetriever([shared_doc_bm25, bm25_only_doc])

    searcher = HybridSearcher(faiss_retriever, bm25_retriever)

    # 동일 ID에 대해 동일 키 생성 확인
    key_faiss = searcher._get_doc_key(shared_doc_faiss)
    key_bm25 = searcher._get_doc_key(shared_doc_bm25)
    assert key_faiss == key_bm25

    results = searcher.search("query", k=10)

    # doc-1은 한 번만 나타나야 함
    ids = [doc["metadata"]["id"] for doc in results]
    assert ids.count("doc-1") == 1
    assert set(ids) == {"doc-1", "doc-2", "doc-3"}


def test_hybrid_searcher_keeps_distinct_docs_with_same_content():
    """내용(content)은 같지만 ID가 다른 문서 유지 검증."""
    faiss_doc = _make_doc("same content", "doc-faiss", source="faiss")
    bm25_doc = _make_doc("same content", "doc-bm25", source="bm25")

    faiss_retriever = StaticRetriever([faiss_doc])
    bm25_retriever = StaticRetriever([bm25_doc])

    searcher = HybridSearcher(faiss_retriever, bm25_retriever)

    # 다른 ID에 대해 다른 키 생성 확인
    key_faiss = searcher._get_doc_key(faiss_doc)
    key_bm25 = searcher._get_doc_key(bm25_doc)
    assert key_faiss != key_bm25

    results = searcher.search("query", k=10)

    # 내용이 같아도 ID가 다르면 별개 문서로 유지
    ids = [doc["metadata"]["id"] for doc in results]
    assert set(ids) == {"doc-faiss", "doc-bm25"}
    assert len(results) == 2

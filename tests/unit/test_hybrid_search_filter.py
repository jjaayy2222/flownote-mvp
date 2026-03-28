import pytest
from backend.hybrid_search import HybridSearcher
from typing import List, Dict, Any, Optional
from backend.utils import check_metadata_match


class StaticRetriever:
    """고정된 검색 결과를 반환하는 리트리버 (테스트용)."""

    def __init__(self, results: List[Dict[str, Any]]):
        self._results = results

    def search(
        self, query: str, k: int, metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        filtered = self._results
        if metadata_filter:
            filtered = [
                doc
                for doc in self._results
                if check_metadata_match(doc.get("metadata", {}), metadata_filter)
            ]
        return filtered[:k]


def _make_doc(content: str, **metadata: Any) -> Dict[str, Any]:
    return {"content": content, "metadata": metadata, "score": 1.0}


def test_hybrid_searcher_para_category_filtering():
    """PARA 카테고리 필터링이 하이브리드 검색에서 정상 작동하는지 검증."""
    docs_faiss = [
        _make_doc("Project Alpha note", category="Projects"),
        _make_doc("Area Health note", category="Areas"),
        _make_doc("Resource Python note", category="Resources"),
    ]
    docs_bm25 = [
        _make_doc("Project Beta note", category="Projects"),
        _make_doc("Archive Old note", category="Archives"),
    ]

    retriever_faiss = StaticRetriever(docs_faiss)
    retriever_bm25 = StaticRetriever(docs_bm25)
    searcher = HybridSearcher(retriever_faiss, retriever_bm25)

    # 1. 'Projects' 카테고리만 필터링
    results = searcher.search("note", k=10, metadata_filter={"category": "Projects"})

    # 두 리트리버에서 Projects 카테고리인 문서들만 모여야 함
    assert len(results) == 2
    for r in results:
        assert r["metadata"]["category"] == "Projects"

    contents = [r["content"] for r in results]
    assert "Project Alpha note" in contents
    assert "Project Beta note" in contents

    # 2. 여러 카테고리 선택 (리스트 필터)
    results_multiple = searcher.search(
        "note", k=10, metadata_filter={"category": ["Areas", "Resources"]}
    )
    assert len(results_multiple) == 2
    categories = {r["metadata"]["category"] for r in results_multiple}
    assert categories == {"Areas", "Resources"}


def test_hybrid_searcher_filtering_returns_empty_when_no_match():
    """필터 조건에 맞는 문서가 없을 때 빈 결과를 반환하는지 검증."""
    docs = [_make_doc("some content", category="Projects")]
    retriever = StaticRetriever(docs)
    searcher = HybridSearcher(retriever, StaticRetriever([]))

    results = searcher.search("query", k=10, metadata_filter={"category": "Archives"})
    assert results == []


def test_hybrid_searcher_filtering_with_other_metadata():
    """카테고리 외 다른 메타데이터 필드 필터링 검증."""
    docs = [
        _make_doc("note 1", source="manual.pdf", priority=1),
        _make_doc("note 2", source="auto.log", priority=2),
    ]
    retriever = StaticRetriever(docs)
    searcher = HybridSearcher(retriever, StaticRetriever([]))

    # source 필터
    results = searcher.search("note", k=10, metadata_filter={"source": "manual.pdf"})
    assert len(results) == 1
    assert results[0]["content"] == "note 1"

    # 복합 필터
    results_complex = searcher.search(
        "note", k=10, metadata_filter={"source": "auto.log", "priority": 2}
    )
    assert len(results_complex) == 1
    assert results_complex[0]["content"] == "note 2"

    # 복합 필터 (불일치)
    results_mismatch = searcher.search(
        "note", k=10, metadata_filter={"source": "manual.pdf", "priority": 2}
    )
    assert results_mismatch == []


def test_hybrid_searcher_list_metadata_filtering():
    """문서 메타데이터가 리스트인 경우(예: tags)의 필터링 검증."""
    docs = [
        _make_doc("AI Note", tags=["AI", "NLP"], category="Tech"),
        _make_doc("Tech Note", tags=["Tech", "Coding"], category="Tech"),
        _make_doc("General Note", tags=["General"], category="News"),
    ]
    retriever = StaticRetriever(docs)
    searcher = HybridSearcher(retriever, StaticRetriever([]))

    # 1. 리스트(Doc) vs 리스트(Filter): 교집합 존재하면 매칭
    results = searcher.search("query", k=10, metadata_filter={"tags": ["AI", "Search"]})
    assert len(results) == 1
    assert results[0]["content"] == "AI Note"

    # 2. 리스트(Doc) vs 스칼라(Filter): 필터값이 문서 리스트에 포함되면 매칭
    results = searcher.search("query", k=10, metadata_filter={"tags": "Coding"})
    assert len(results) == 1
    assert results[0]["content"] == "Tech Note"

    # 3. 스칼라(Doc) vs 리스트(Filter): 문서값이 필터 리스트에 포함되면 매칭
    results = searcher.search(
        "query", k=10, metadata_filter={"category": ["News", "Sports"]}
    )
    assert len(results) == 1
    assert results[0]["content"] == "General Note"

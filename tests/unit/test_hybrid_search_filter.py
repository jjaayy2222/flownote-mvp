import pytest
from backend.hybrid_search import HybridSearcher
from typing import List, Dict, Any, Optional


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
                if self._check_metadata(doc.get("metadata", {}), metadata_filter)
            ]
        return filtered[:k]

    def _check_metadata(
        self, doc_metadata: Dict[str, Any], metadata_filter: Dict[str, Any]
    ) -> bool:
        for key, value in metadata_filter.items():
            doc_val = doc_metadata.get(key)
            if isinstance(value, list):
                if doc_val not in value:
                    return False
            else:
                if doc_val != value:
                    return False
        return True


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

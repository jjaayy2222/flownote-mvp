import pytest
from backend.bm25_search import BM25Retriever


def test_bm25_retriever_filtering():
    """BM25Retriever의 실제 필터링 로직 작동 여부 검증."""
    retriever = BM25Retriever()

    docs = [
        {"content": "apple banana", "metadata": {"category": "fruit", "color": "red"}},
        {
            "content": "banana cherry",
            "metadata": {"category": "fruit", "color": "yellow"},
        },
        {"content": "cherry date", "metadata": {"category": "fruit", "color": "red"}},
        {
            "content": "carrot egg",
            "metadata": {"category": "vegetable", "color": "orange"},
        },
        {"content": "extra doc 1", "metadata": {"category": "other"}},
        {"content": "extra doc 2", "metadata": {"category": "other"}},
    ]

    retriever.add_documents(docs)

    # 1. 'fruit' 카테고리만 검색
    results = retriever.search("banana", k=10, metadata_filter={"category": "fruit"})
    assert len(results) == 2
    for r in results:
        assert r["metadata"]["category"] == "fruit"
        assert "banana" in r["content"]

    # 2. 'red' 색상만 검색 (banana cherry 제외되어야 함)
    results_red = retriever.search(
        "banana cherry", k=10, metadata_filter={"color": "red"}
    )
    assert len(results_red) == 2
    for r in results_red:
        assert r["metadata"]["color"] == "red"

    contents_red = [r["content"] for r in results_red]
    assert "apple banana" in contents_red
    assert "cherry date" in contents_red

    # 3. 리스트 필터링
    # 'banana'는 yellow 문서에, 'carrot'은 orange 문서에 매칭되어 두 문서 모두 반환되어야 함
    results_list = retriever.search(
        "banana carrot", k=10, metadata_filter={"color": ["yellow", "orange"]}
    )
    assert len(results_list) == 2
    colors_list = {r["metadata"]["color"] for r in results_list}
    assert colors_list == {"yellow", "orange"}


def test_bm25_retriever_filtering_empty_results():
    """조건에 맞는 문서가 없을 때 빈 결과 반환."""
    retriever = BM25Retriever()
    retriever.add_documents([{"content": "test", "metadata": {"a": 1}}])

    assert retriever.search("test", k=10, metadata_filter={"a": 2}) == []
    assert retriever.search("test", k=10, metadata_filter={"b": 1}) == []

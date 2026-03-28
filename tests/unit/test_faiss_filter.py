import pytest
import numpy as np
import numbers
from typing import Optional, Dict
from unittest.mock import patch, MagicMock
from backend.faiss_search import FAISSRetriever


@pytest.fixture
def faiss_retriever():
    with patch("backend.embedding.EmbeddingGenerator.generate_embeddings") as mock_gen:
        # Mock embedding return (1536 dim)
        mock_gen.return_value = {
            "embeddings": [[0.1] * 1536],
            "tokens": 10,
            "cost": 0.0,
        }
        retriever = FAISSRetriever()
        yield retriever


def test_faiss_retriever_filtering(faiss_retriever):
    """FAISSRetriever의 메타데이터 필터링 작동 여부 검증."""
    docs = [
        {"content": "Project Note", "metadata": {"category": "Projects", "id": 1}},
        {"content": "Area Note", "metadata": {"category": "Areas", "id": 2}},
        {"content": "Resource Note", "metadata": {"category": "Resources", "id": 3}},
    ]
    embeddings = np.array([[0.1] * 1536, [0.5] * 1536, [0.9] * 1536], dtype=np.float32)
    faiss_retriever.add_documents(embeddings, docs)

    results = faiss_retriever.search(
        "query", k=10, metadata_filter={"category": "Projects"}
    )
    assert len(results) == 1
    assert results[0]["metadata"]["category"] == "Projects"
    assert results[0]["content"] == "Project Note"


def test_faiss_retriever_filtering_no_match(faiss_retriever):
    """필터 조건에 맞는 문서가 없을 때 빈 결과 반환."""
    docs = [{"content": "test", "metadata": {"category": "Projects"}}]
    embeddings = np.array([[0.1] * 1536], dtype=np.float32)
    faiss_retriever.add_documents(embeddings, docs)

    results = faiss_retriever.search(
        "query", k=10, metadata_filter={"category": "Archives"}
    )
    assert results == []


def test_faiss_retriever_invalid_expansion_types():
    """확장 배수의 타입 및 범위 유효성 검증."""
    # 1. 수치형이 아닌 경우 (TypeError)
    with pytest.raises(TypeError, match="real number"):
        FAISSRetriever(filter_expansion_factor="10")

    # 2. 불리언인 경우 (TypeError)
    with pytest.raises(TypeError, match="real number"):
        FAISSRetriever(filter_expansion_factor=True)

    # 3. 1 미만인 경우 (ValueError)
    with pytest.raises(ValueError, match="expansion_factor"):
        FAISSRetriever(filter_expansion_factor=0)

    # 4. 정규화(int 캐스팅) 후 1 미만이 되는 경우 (ValueError)
    with pytest.raises(ValueError, match="expansion_factor"):
        FAISSRetriever(filter_expansion_factor=0.5)


def test_faiss_retriever_invalid_expansion_search():
    """검색 시 확장 배수 유효성 검사 (필터 유무에 따른 차이)"""
    retriever = FAISSRetriever()

    # 1. metadata_filter가 None이면 검증 건너뜀 (리뷰어 요청 반영)
    retriever.search("query", metadata_filter=None, filter_expansion_factor=-1)

    # 2. metadata_filter가 있으면 (빈 딕셔너리 포함) 검증 수행
    with pytest.raises(ValueError, match="must be >= 1"):
        retriever.search("query", metadata_filter={}, filter_expansion_factor=-1)

    with pytest.raises(ValueError, match="must be >= 1"):
        retriever.search("query", metadata_filter={"id": 1}, filter_expansion_factor=0)


def test_faiss_retriever_list_metadata_filtering(faiss_retriever):
    """FAISS에서 리스트형 메타데이터(tags 등)의 다양한 매칭 케이스 검증."""
    docs = [
        {"content": "AI Note", "metadata": {"tags": ["AI", "NLP"], "status": "active"}},
        {
            "content": "Tech Note",
            "metadata": {"tags": ["Tech", "Coding"], "status": "pending"},
        },
        {"content": "Solo Note", "metadata": {"tags": "General", "status": "active"}},
    ]
    embeddings = np.array([[0.1] * 1536, [0.5] * 1536, [0.9] * 1536], dtype=np.float32)
    faiss_retriever.add_documents(embeddings, docs)

    # 케이스 1: 리스트(Doc) vs 리스트(Filter) - 교집합
    results1 = faiss_retriever.search(
        "query", k=10, metadata_filter={"tags": ["AI", "Search"]}
    )
    assert len(results1) == 1
    assert results1[0]["content"] == "AI Note"

    # 케이스 2: 리스트(Doc) vs 스칼라(Filter) - 포함 여부
    results2 = faiss_retriever.search("query", k=10, metadata_filter={"tags": "Coding"})
    assert len(results2) == 1
    assert results2[0]["content"] == "Tech Note"

    # 케이스 3: 스칼라(Doc) vs 리스트(Filter) - 필터 리스트에 포함 여부
    results3 = faiss_retriever.search(
        "query", k=10, metadata_filter={"tags": ["General", "Personal"]}
    )
    assert len(results3) == 1
    assert results3[0]["content"] == "Solo Note"


def test_faiss_retriever_unhashable_metadata_filtering(faiss_retriever):
    """해시 불가능한 객체(dict 등)가 포함된 메타데이터 필터링 검색 검증."""
    docs = [
        {
            "content": "Dict Tag Note",
            "metadata": {"tags": [{"id": "t1", "name": "AI"}]},
        },
        {"content": "Normal Note", "metadata": {"tags": ["Tech"]}},
    ]
    embeddings = np.array([[0.1] * 1536, [0.5] * 1536], dtype=np.float32)
    faiss_retriever.add_documents(embeddings, docs)

    # 리스트 내에 dict가 있어도 set() 변환 에러 없이 정상 매칭되어야 함
    results = faiss_retriever.search(
        "query", k=10, metadata_filter={"tags": [{"id": "t1", "name": "AI"}]}
    )
    assert len(results) == 1
    assert results[0]["content"] == "Dict Tag Note"

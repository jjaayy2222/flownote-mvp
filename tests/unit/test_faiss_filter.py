import pytest
import numpy as np
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


def test_faiss_retriever_post_filtering_fetch_more(faiss_retriever):
    """필터링을 위해 내부적으로 더 많은 후보군을 가져오는지 로직 검증."""
    docs = [{"content": f"note {i}", "metadata": {"match": i == 19}} for i in range(20)]
    embeddings = np.array(
        [[0.1 + i * 0.01] * 1536 for i in range(20)], dtype=np.float32
    )
    faiss_retriever.add_documents(embeddings, docs)

    # k=1 이고 기본 확장 10이면 0-9만 보므로 19번 안 나옴
    results = faiss_retriever.search("query", k=1, metadata_filter={"match": True})
    assert results == []

    # k=2 이면 2*10=20개 보므로 19번 나옴
    results_k2 = faiss_retriever.search("query", k=2, metadata_filter={"match": True})
    assert len(results_k2) == 1
    assert results_k2[0]["content"] == "note 19"


def test_faiss_retriever_configurable_expansion(faiss_retriever):
    """필터 확장 배수가 유동적으로 적용되는지 검증."""
    docs = [{"content": f"note {i}", "metadata": {"match": i == 19}} for i in range(20)]
    embeddings = np.array(
        [[0.1 + i * 0.01] * 1536 for i in range(20)], dtype=np.float32
    )
    faiss_retriever.add_documents(embeddings, docs)

    # 1. 기본값 10: k=1 -> 10개 -> 19번 미발견
    assert faiss_retriever.search("query", k=1, metadata_filter={"match": True}) == []

    # 2. 오버라이드 20: k=1 -> 20개 -> 19번 발견
    results = faiss_retriever.search(
        "query", k=1, metadata_filter={"match": True}, filter_expansion_factor=20
    )
    assert len(results) == 1
    assert results[0]["content"] == "note 19"


def test_faiss_retriever_invalid_expansion():
    """유효하지 않은 확장 배수 설정 시 예외 발생 검증."""
    with pytest.raises(ValueError, match="filter_expansion_factor must be >= 1"):
        FAISSRetriever(filter_expansion_factor=0)

    retriever = FAISSRetriever()
    with pytest.raises(ValueError, match="filter_expansion_factor must be >= 1"):
        retriever.search("query", filter_expansion_factor=-1)


def test_faiss_retriever_list_metadata_filtering(faiss_retriever):
    """FAISS에서 리스트형 메타데이터(tags 등) 필터링 검증."""
    docs = [
        {"content": "AI Note", "metadata": {"tags": ["AI", "NLP"]}},
        {"content": "Tech Note", "metadata": {"tags": ["Tech", "Coding"]}},
    ]
    embeddings = np.array([[0.1] * 1536, [0.5] * 1536], dtype=np.float32)
    faiss_retriever.add_documents(embeddings, docs)

    # 리스트 vs 리스트 매칭 (교집합)
    results = faiss_retriever.search(
        "query", k=10, metadata_filter={"tags": ["AI", "Search"]}
    )
    assert len(results) == 1
    assert results[0]["content"] == "AI Note"

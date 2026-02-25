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
    # 1. 문서 준비
    docs = [
        {"content": "Project Note", "metadata": {"category": "Projects", "id": 1}},
        {"content": "Area Note", "metadata": {"category": "Areas", "id": 2}},
        {"content": "Resource Note", "metadata": {"category": "Resources", "id": 3}},
    ]
    # 각 문서에 대해 다른 임베딩을 시뮬레이션하기 위해 수동으로 add_documents 호출
    # (실제 임베딩 생성은 패치하지 않고 직접 넘파이 배열 전달)
    embeddings = np.array([[0.1] * 1536, [0.5] * 1536, [0.9] * 1536], dtype=np.float32)
    faiss_retriever.add_documents(embeddings, docs)

    # 2. 'Projects' 필터 적용 검색
    # search 내부에서 query 임베딩을 위해 generate_embeddings가 호출되는데 fixture에서 패치됨
    results = faiss_retriever.search(
        "query", k=10, metadata_filter={"category": "Projects"}
    )

    assert len(results) == 1
    assert results[0]["metadata"]["category"] == "Projects"
    assert results[0]["content"] == "Project Note"

    # 3. 리스트 필터 적용
    results_list = faiss_retriever.search(
        "query", k=10, metadata_filter={"category": ["Areas", "Resources"]}
    )
    assert len(results_list) == 2
    categories = {r["metadata"]["category"] for r in results_list}
    assert categories == {"Areas", "Resources"}


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
    """필터링을 위해 내부적으로 더 많은 후보군(k*10)을 가져오는지 로직 검증."""
    # 20개의 문서를 넣고, 검색 결과 1개를 요청하지만 필터에 걸려 뒤쪽 문서가 나와야 하는 상황
    docs = [{"content": f"note {i}", "metadata": {"match": i == 19}} for i in range(20)]
    # 거리를 다르게 하여 i=0이 가장 가깝게 설정
    embeddings = np.array(
        [[0.1 + i * 0.01] * 1536 for i in range(20)], dtype=np.float32
    )
    faiss_retriever.add_documents(embeddings, docs)

    # k=1 이지만 match=True인 문서는 가장 먼 19번 문서뿐임.
    # 만약 k=1만큼만 내부적으로 검색하면 0번 문서가 나오고 필터에서 걸려 빈 결과가 나오겠지만,
    # k*10 (10개) 이상을 가져오면 19번까지는 못 가더라도...
    # 아, 20개 중 k*10=10개면 19번까지 못 가겠네요.
    # k=2 정도로 해서 k*10=20개를 가져오게 하면 19번 문서가 포함되어야 함.
    results = faiss_retriever.search("query", k=1, metadata_filter={"match": True})

    # k=1 인데 k*10=10 개를 가져오면 index 0~9 까지만 확인하므로 19번은 안 나옴. -> 빈 결과 정상
    assert results == []

    # k=2 이면 k*10=20 개를 가져오므로 index 0~19 다 확인하여 19번이 나옴.
    results_k2 = faiss_retriever.search("query", k=2, metadata_filter={"match": True})
    assert len(results_k2) == 1
    assert results_k2[0]["content"] == "note 19"

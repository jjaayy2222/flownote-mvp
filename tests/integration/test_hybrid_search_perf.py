import logging
import numpy as np
import time
from unittest.mock import patch
from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever
from backend.hybrid_search import HybridSearcher
from backend.utils import check_metadata_match

logger = logging.getLogger(__name__)


def generate_test_dataset(size=100):
    """
    테스트를 위한 '실제 데이터셋' 스타일의 데이터 생성.
    시드를 고정하여 결과의 재현성을 보장합니다.
    """
    np.random.seed(42)
    topics = {
        "AI": [
            "machine learning",
            "neural networks",
            "large language models",
            "deep learning",
            "transformers",
        ],
        "Coding": [
            "python programming",
            "javascript frameworks",
            "database optimization",
            "system design",
            "git workflow",
        ],
        "Personal": [
            "daily journal",
            "health goals",
            "travel planning",
            "financial records",
            "hobby projects",
        ],
        "Business": [
            "quarterly reports",
            "client meeting notes",
            "project timelines",
            "market analysis",
            "budget planning",
        ],
    }
    categories = ["Projects", "Areas", "Resources", "Archives"]

    docs = []
    embeddings = []

    for i in range(size):
        topic = list(topics.keys())[i % len(topics)]
        subtheme = topics[topic][(i // len(topics)) % len(topics[topic])]
        category = categories[i % len(categories)]

        content = f"This document is about {subtheme} in the context of {topic}. Document number {i}."
        metadata = {
            "id": f"doc_{i}",
            "topic": topic,
            "category": category,
            "tags": [topic, subtheme.split()[0]],
        }

        docs.append({"content": content, "metadata": metadata})
        embeddings.append(np.random.rand(1536).astype("float32"))

    return docs, np.array(embeddings)


def test_hybrid_search_quality_and_performance():
    """
    [통합 테스트] 실제 규모의 데이터셋을 활용한 하이브리드 검색 성능 및 품질 측정.
    - 검색 속도(Latency) 측정 및 필터링 정확도 확인
    - 모킹 패치의 격리를 위해 컨텍스트 매니저 사용
    """
    logger.info("하이브리드 검색 통합 성능 측정 시작")

    # 1. 데이터 준비
    num_docs = 200
    docs, embeddings = generate_test_dataset(size=num_docs)

    faiss_retriever = FAISSRetriever()
    bm25_retriever = BM25Retriever()
    hybrid_searcher = HybridSearcher(faiss_retriever, bm25_retriever)

    # patch를 with 구문으로 감싸서 리소스 누수 및 테스트 오염 방지
    with patch("backend.embedding.EmbeddingGenerator.generate_embeddings") as mock_emb:
        mock_emb.return_value = {
            "embeddings": [np.random.rand(1536).tolist()],
            "tokens": 10,
            "cost": 0.0,
        }

        # 2. 인덱싱 시간 측정
        start_time = time.time()
        faiss_retriever.add_documents(embeddings, docs)
        bm25_retriever.add_documents(docs)
        indexing_time = time.time() - start_time
        logger.info(f"인덱싱 완료: {num_docs}개 문서 (소요 시간: {indexing_time:.4f}s)")

        # 3. 검색 쿼리 수행 및 성능 측정
        test_queries = [
            {"q": "machine learning AI", "filter": {"category": "Projects"}},
            {"q": "python programming", "filter": {"topic": "Coding"}},
            {"q": "financial budget planning", "filter": None},
            {"q": "git workflow", "filter": {"category": ["Resources", "Areas"]}},
        ]

        for test in test_queries:
            query = test["q"]
            m_filter = test["filter"]

            start_search = time.time()
            results = hybrid_searcher.search(
                query, k=5, metadata_filter=m_filter, alpha=0.5
            )
            search_time = time.time() - start_search

            logger.info(
                f"Query: '{query}' | Filter: {m_filter} | Latency: {search_time*1000:.2f}ms"
            )

            if m_filter:
                for r in results:
                    assert check_metadata_match(r["metadata"], m_filter) is True

        # 4. 알파(alpha) 값 변화에 따른 최적화 실험
        query_opt = "machine learning"
        res_dense = hybrid_searcher.search(query_opt, k=3, alpha=1.0)
        res_sparse = hybrid_searcher.search(query_opt, k=3, alpha=0.0)

        logger.info(f"Alpha Optimization Check Done for query: '{query_opt}'")
        assert len(res_dense) > 0 or len(res_sparse) > 0

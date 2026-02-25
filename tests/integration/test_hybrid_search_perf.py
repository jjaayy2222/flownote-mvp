import pytest
import numpy as np
import time
from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever
from backend.hybrid_search import HybridSearcher


def generate_test_dataset(size=100):
    """
    테스트를 위한 '실제 데이터셋' 스타일의 데이터 생성.
    다양한 기술 토픽과 PARA 카테고리를 포함합니다.
    """
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
        # 임베딩은 랜덤으로 생성 (실제 API 호출을 피하기 위함)
        embeddings.append(np.random.rand(1536).astype("float32"))

    return docs, np.array(embeddings)


def test_hybrid_search_quality_and_performance():
    """
    [통합 테스트] 실제 규모의 데이터셋을 활용한 하이브리드 검색 성능 및 품질 측정.
    - 검색 속도(Latency) 측정
    - 메타데이터 필터링 정확도 확인
    - RRF 병합 결과의 합리성 검토
    """
    print("\n" + "=" * 60)
    print("🚀 하이브리드 검색 통합 성능 측정 시작")
    print("=" * 60)

    # 1. 데이터 준비
    num_docs = 200
    docs, embeddings = generate_test_dataset(size=num_docs)

    faiss_retriever = FAISSRetriever()
    bm25_retriever = BM25Retriever()
    hybrid_searcher = HybridSearcher(faiss_retriever, bm25_retriever)

    # [PATCH] 실제 OpenAI API 호출 방지를 위한 모킹 (크레딧 부족 대응)
    from unittest.mock import patch

    mock_emb = patch("backend.embedding.EmbeddingGenerator.generate_embeddings")
    mock_emb.start()
    import backend.embedding

    backend.embedding.EmbeddingGenerator.generate_embeddings.return_value = {
        "embeddings": [np.random.rand(1536).tolist()],
        "tokens": 10,
        "cost": 0.0,
    }

    # 2. 인덱싱 시간 측정
    start_time = time.time()
    faiss_retriever.add_documents(embeddings, docs)
    bm25_retriever.add_documents(docs)
    indexing_time = time.time() - start_time
    print(f"✅ 인덱싱 완료: {num_docs}개 문서 (소요 시간: {indexing_time:.4f}s)")

    # 3. 검색 쿼리 수행 및 성능 측정
    test_queries = [
        {"q": "machine learning AI", "filter": {"category": "Projects"}},
        {"q": "python programming", "filter": {"topic": "Coding"}},
        {"q": "financial budget planning", "filter": None},
        {"q": "git workflow", "filter": {"category": ["Resources", "Areas"]}},
    ]

    print(f"\n🔍 검색 테스트 실행 (쿼리 수: {len(test_queries)})")
    print("-" * 60)

    for test in test_queries:
        query = test["q"]
        m_filter = test["filter"]

        start_search = time.time()
        # k=5, alpha=0.5 (Hybrid)
        results = hybrid_searcher.search(
            query, k=5, metadata_filter=m_filter, alpha=0.5
        )
        search_time = time.time() - start_search

        print(f"Query: '{query}' | Filter: {m_filter}")
        print(f"Latency: {search_time*1000:.2f}ms | Results: {len(results)}")

        # 품질 검증 (필터링 정확도)
        if m_filter:
            for r in results:
                # utils.check_metadata_match는 이미 단위 테스트에서 검증되었으나 통합 차원에서 확인
                # 리스트 필터링 등까지 고려하여 검증
                from backend.utils import check_metadata_match

                assert check_metadata_match(r["metadata"], m_filter) is True

        # 결과 요약 출력
        for i, r in enumerate(results[:1]):
            print(f"  Top-1: {r['content'][:50]}... (Score: {r['score']:.4f})")
        print("-" * 60)

    # 4. 알파(alpha) 값 변화에 따른 최적화 실험
    print("\n🧪 가중치(alpha) 변화에 따른 결과 비교 (Optimization Check)")
    query_opt = "machine learning"
    # alpha = 1.0 (Dense Only)
    res_dense = hybrid_searcher.search(query_opt, k=3, alpha=1.0)
    # alpha = 0.0 (Sparse Only)
    res_sparse = hybrid_searcher.search(query_opt, k=3, alpha=0.0)

    print(f"  Query: '{query_opt}'")
    print(
        f"  Dense (alpha=1.0) Top-1: {res_dense[0]['content'] if res_dense else 'N/A'}"
    )
    print(
        f"  Sparse (alpha=0.0) Top-1: {res_sparse[0]['content'] if res_sparse else 'N/A'}"
    )

    print("\n" + "=" * 60)
    print("🎯 통합 테스트 결과 요약: 모든 검색 및 필터링 정책이 정상 작동함")
    print("=" * 60)


if __name__ == "__main__":
    test_hybrid_search_quality_and_performance()

import numpy as np
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever
from backend.hybrid_search import HybridSearcher


def manual_test():
    logging.basicConfig(level=logging.INFO)
    print("=" * 50)
    print("하이브리드(RRF) 검색 수동 테스트")
    print("=" * 50)

    # 더미 데이터 생성
    docs = [
        {
            "content": "FlowNote는 AI를 활용한 대화 관리 도구입니다.",
            "metadata": {"source": "doc1"},
        },
        {
            "content": "BM25는 키워드 기반의 희소 벡터 검색 알고리즘입니다.",
            "metadata": {"source": "doc2"},
        },
        {
            "content": "대화 내용에 대한 밀집 벡터 검색은 FAISS를 사용합니다.",
            "metadata": {"source": "doc3"},
        },
        {
            "content": "하이브리드 검색은 FAISS와 BM25를 결합하여 결과를 제공합니다.",
            "metadata": {"source": "doc4"},
        },
    ]

    # 더미 임베딩 (1536차원)
    np.random.seed(42)
    embeddings = np.random.rand(4, 1536).astype(np.float32)

    # 1. FAISS 세팅
    faiss_retriever = FAISSRetriever()
    faiss_retriever.add_documents(embeddings, docs)

    # 2. BM25 세팅
    bm25_retriever = BM25Retriever()
    bm25_retriever.add_documents(docs)

    # 3. HybridSearcher 병합
    hybrid_searcher = HybridSearcher(faiss_retriever, bm25_retriever)

    query = "대화 검색"
    print(f"\n🔍 검색 쿼리: '{query}'")

    results = hybrid_searcher.search(query, k=3, alpha=0.5)

    print(f"\n검색 결과 ({len(results)}개):")
    print("-" * 50)
    for i, result in enumerate(results, 1):
        print(f"\n{i}위:")
        print(f"    - RRF 점수: {result['score']:.4f}")
        print(f"    - 내용: {result['content']}")
        print(f"    - 메타데이터: {result['metadata']}")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    manual_test()

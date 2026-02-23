# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/hybrid_search.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 하이브리드 검색 및 RRF 병합 모듈
"""

from typing import List, Dict, Any, Optional
from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever


class HybridSearcher:
    """FAISS(Dense)와 BM25(Sparse)의 결과를 RRF로 병합하는 검색기"""

    def __init__(
        self,
        faiss_retriever: FAISSRetriever,
        bm25_retriever: BM25Retriever,
        rrf_k: int = 60,
    ):
        """
        Args:
            faiss_retriever: 초기화된 FAISS 리트리버 인스턴스
            bm25_retriever: 초기화된 BM25 리트리버 인스턴스
            rrf_k: RRF 페널티 상수 (보통 60 사용)
        """
        self.faiss_retriever = faiss_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k

    def search(
        self,
        query: str,
        k: int = 3,
        faiss_k: Optional[int] = None,
        bm25_k: Optional[int] = None,
        alpha: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        하이브리드 검색 수행 후 RRF 점수로 정렬하여 반환

        Args:
            query: 검색 질의
            k: 최종 반환할 문서 수
            faiss_k: FAISS에서 가져올 후보 수 (기본값: k * 2)
            bm25_k: BM25에서 가져올 후보 수 (기본값: k * 2)
            alpha: FAISS 점수 가중치, (1-alpha)는 BM25 점수 가중치 (기본값: 0.5)

        Returns:
            정렬된 하이브리드 검색 결과 리스트 (content, metadata, score 포함)
        """
        faiss_candidates = faiss_k or (k * 2)
        bm25_candidates = bm25_k or (k * 2)

        # 1. 각 검색 엔진에서 결과 가져오기
        faiss_results = self.faiss_retriever.search(query, k=faiss_candidates)
        bm25_results = self.bm25_retriever.search(query, k=bm25_candidates)

        # 2. RRF 병합 식별을 위한 Dictionary 정리
        rrf_scores: Dict[str, float] = {}
        merged_docs: Dict[str, Dict[str, Any]] = {}

        # FAISS 결과 RRF에 반영 (가중치: alpha)
        for rank, res in enumerate(faiss_results, 1):
            # content 값 자체를 임시 고유 식별자로 사용
            doc_key = res["content"]
            if doc_key not in rrf_scores:
                rrf_scores[doc_key] = 0.0
                merged_docs[doc_key] = {
                    "content": res["content"],
                    "metadata": res.get("metadata", {}),
                }
            rrf_scores[doc_key] += alpha * (1.0 / (self.rrf_k + rank))

        # BM25 결과 RRF에 반영 (가중치: 1.0 - alpha)
        for rank, res in enumerate(bm25_results, 1):
            doc_key = res["content"]
            if doc_key not in rrf_scores:
                rrf_scores[doc_key] = 0.0
                merged_docs[doc_key] = {
                    "content": res["content"],
                    "metadata": res.get("metadata", {}),
                }
            rrf_scores[doc_key] += (1.0 - alpha) * (1.0 / (self.rrf_k + rank))

        # 3. 계산된 RRF 점수로 내림차순 정렬
        sorted_keys = sorted(
            rrf_scores.keys(), key=lambda key: rrf_scores[key], reverse=True
        )

        final_results = []
        for doc_key in sorted_keys[:k]:
            doc_info = merged_docs[doc_key].copy()
            doc_info["score"] = rrf_scores[doc_key]
            final_results.append(doc_info)

        return final_results


if __name__ == "__main__":
    import numpy as np

    print("=" * 50)
    print("하이브리드(RRF) 검색 테스트")
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

    # 더미 임베딩 (1536차원) - 텍스트 임베딩 차원 고정을 위해 랜덤 생성
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

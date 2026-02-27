# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/hybrid_search.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 하이브리드 검색 및 RRF 병합 모듈
"""

import hashlib
import logging
from typing import List, Dict, Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Retriever(Protocol):
    """
    리트리버 인터페이스 정의.
    HybridSearcher가 사용하는 모든 리트리버는 이 프로토콜을 준수해야 합니다.
    """

    def search(
        self, query: str, k: int, metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        검색을 수행하고 정렬된 리스트를 반환합니다.

        반환 리스트의 각 요소는 최소한 다음 필드를 포함해야 합니다:
        - content: 문서 내용 (str)
        - metadata: 관련 메타데이터 (dict)
        - score: 검색 점수 (float, 내림차순 정렬 가정)
          (참고: RRF는 절대 점수가 아닌 순위(Rank)를 기반으로 작동하지만,
          인터페이스 일관성을 위해 score 필드 포함을 권장합니다.)

        Args:
            query: 검색 질의
            k: 반환할 결과 수
            metadata_filter: 메타데이터 필터 조건 (예: {"category": "Projects"})
        """
        ...


class HybridSearcher:
    """
    FAISS(Dense)와 BM25(Sparse)의 결과를 RRF(Reciprocal Rank Fusion)로 병합하는 검색기.

    계약 및 전제 조건:
    - 주입되는 리트리버는 `search` 메서드를 통해 점수 내림차순으로 정렬된 결과를 반환해야 합니다.
    - RRF는 결과의 절대적인 점수가 아닌 '순위(Rank)'만을 사용하여 병합하므로,
      두 검색 엔진의 스케일이 달라도 안정적인 병합이 가능합니다.
    """

    def __init__(
        self,
        faiss_retriever: Retriever,
        bm25_retriever: Retriever,
        rrf_k: int = 60,
    ):
        """
        Args:
            faiss_retriever: search() 메서드를 가진 Dense 리트리버
            bm25_retriever: search() 메서드를 가진 Sparse 리트리버
            rrf_k: RRF 페널티 상수 (기본값: 60, 0보다 커야 함).
                  값이 클수록 고순위 문서 간의 점수 차이가 완만해집니다.
        """
        if rrf_k <= 0:
            raise ValueError(f"rrf_k must be positive, got {rrf_k}")

        self.faiss_retriever = faiss_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k

    def _get_doc_key(self, doc: Dict[str, Any]) -> str:
        """
        문서 식별을 위한 고유 키 생성 (ID 우선, 없을 경우 해시)
        """
        metadata = doc.get("metadata")
        if isinstance(metadata, dict) and "id" in metadata:
            return str(metadata["id"])

        # ID가 없는 경우 내용과 메타데이터 정보를 조합해 해시 생성
        content = str(doc.get("content", ""))
        source = ""
        chunk_idx = ""
        if isinstance(metadata, dict):
            source = str(metadata.get("source", ""))
            chunk_idx = str(metadata.get("chunk_index", ""))

        combined = f"{content}::{source}::{chunk_idx}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def search(
        self,
        query: str,
        k: int = 3,
        faiss_k: Optional[int] = None,
        bm25_k: Optional[int] = None,
        alpha: float = 0.5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        하이브리드 검색 수행 후 RRF 점수로 정렬하여 반환

        Args:
            query: 검색 질의
            k: 최종 반환할 문서 수 (0 이상)
            faiss_k: FAISS에서 가져올 후보 수 (기본값: k * 2, 0 이상)
            bm25_k: BM25에서 가져올 후보 수 (기본값: k * 2, 0 이상)
            alpha: [0, 1] 범위의 가중치. 1.0에 가까울수록 Dense(FAISS) 결과 비중이 커짐.
            metadata_filter: 메타데이터 필터 조건 (예: {"category": "Projects"})

        Returns:
            RRF 점수 기반으로 재정렬된 하이브리드 검색 결과 리스트 (content, metadata, score 포함)
        """
        # 검사항목 1: 파라미터 유효 범위 검증
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha must be between 0 and 1 (inclusive), got {alpha}")

        if k < 0:
            raise ValueError(f"k must be non-negative, got {k}")

        if k == 0:
            return []

        # 개별 k 값에 대한 음수 검증
        if faiss_k is not None and faiss_k < 0:
            raise ValueError(f"faiss_k must be non-negative, got {faiss_k}")
        if bm25_k is not None and bm25_k < 0:
            raise ValueError(f"bm25_k must be non-negative, got {bm25_k}")

        # None 여부 명시적 확인 (0을 허용하기 위함)
        f_k = faiss_k if faiss_k is not None else (k * 2)
        b_k = bm25_k if bm25_k is not None else (k * 2)

        # 1. 각 검색 엔진에서 결과 가져오기
        faiss_results = self.faiss_retriever.search(
            query, k=f_k, metadata_filter=metadata_filter
        )
        bm25_results = self.bm25_retriever.search(
            query, k=b_k, metadata_filter=metadata_filter
        )

        # 2. RRF 병합 식별을 위한 Dictionary 정리
        rrf_scores: Dict[str, float] = {}
        merged_docs: Dict[str, Dict[str, Any]] = {}

        # FAISS 결과 RRF에 반영 (가중치: alpha)
        for rank, res in enumerate(faiss_results, 1):
            doc_key = self._get_doc_key(res)
            if doc_key not in rrf_scores:
                rrf_scores[doc_key] = 0.0
                merged_docs[doc_key] = {
                    "content": res.get("content", ""),
                    "metadata": res.get("metadata", {}),
                }
            rrf_scores[doc_key] += alpha * (1.0 / (self.rrf_k + rank))

        # BM25 결과 RRF에 반영 (가중치: 1.0 - alpha)
        for rank, res in enumerate(bm25_results, 1):
            doc_key = self._get_doc_key(res)
            if doc_key not in rrf_scores:
                rrf_scores[doc_key] = 0.0
                merged_docs[doc_key] = {
                    "content": res.get("content", ""),
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

        # 구조화된 로깅
        logger.info(
            "Hybrid search completed",
            extra={
                "query_len": len(query),
                "alpha": alpha,
                "candidates": len(rrf_scores),
                "returned": len(final_results),
            },
        )

        return final_results

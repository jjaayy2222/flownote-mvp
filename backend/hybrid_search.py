# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/hybrid_search.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 하이브리드 검색 및 RRF 병합 모듈
"""

import hashlib
import logging
from typing import List, Dict, Any, Optional

from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever

logger = logging.getLogger(__name__)


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
            rrf_k: RRF 페널티 상수 (기본값: 60, 0보다 커야 함)
        """
        if rrf_k <= 0:
            raise ValueError(f"rrf_k must be positive, got {rrf_k}")

        self.faiss_retriever = faiss_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k

    def _get_doc_key(self, doc: Dict[str, Any]) -> str:
        """
        문서 식별을 위한 고유 키 생성 (ID 우선, 없을 경우 해시)

        Comment 1, 2 반영: 단순히 content를 키로 쓰지 않고,
        메타데이터(source, index)를 조합해 해싱함으로써 내용 중복 시 충돌 방지.
        """
        metadata = doc.get("metadata")
        if isinstance(metadata, dict) and "id" in metadata:
            return str(metadata["id"])

        # ID가 없는 경우 내용과 메타데이터 정보를 조합해 해시 생성
        # (단순 content 비교 시 발생하는 충돌 방지)
        content = str(doc.get("content", ""))
        source = ""
        chunk_idx = ""
        if isinstance(metadata, dict):
            source = str(metadata.get("source", ""))
            chunk_idx = str(metadata.get("chunk_index", ""))

        # 구분자(::)를 사용하여 필트간 경계 명확화
        combined = f"{content}::{source}::{chunk_idx}"
        return hashlib.sha256(combined.encode()).hexdigest()

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
            alpha: [0, 1] 범위의 FAISS 점수 가중치 (1-alpha는 BM25 가중치)

        Returns:
            정렬된 하이브리드 검색 결과 리스트 (content, metadata, score 포함)
        """
        # [검토 반영] 0. 파라미터 검증
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha must be between 0 and 1 (inclusive), got {alpha}")

        if k <= 0:
            return []

        # Comment 3 반영: None 여부 명시적 확인 (0을 허용하기 위함)
        faiss_candidates = faiss_k if faiss_k is not None else (k * 2)
        bm25_candidates = bm25_k if bm25_k is not None else (k * 2)

        # 1. 각 검색 엔진에서 결과 가져오기
        faiss_results = self.faiss_retriever.search(query, k=faiss_candidates)
        bm25_results = self.bm25_retriever.search(query, k=bm25_candidates)

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
            # [보안] 로깅이나 반환 시 내부 해시 키(doc_key)는 불필요하므로 포함하지 않음
            final_results.append(doc_info)

        # [운영] 구조화된 로깅
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

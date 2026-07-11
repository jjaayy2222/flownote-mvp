# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/hybrid_search.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - 하이브리드 검색 및 RRF 병합 모듈
[EN] FlowNote MVP - Hybrid Search and RRF Merging module
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Retriever(Protocol):
    """
    [KO] 리트리버(Retriever) 인터페이스 정의.
    [EN] Interface definition for a Retriever.

    [KO] HybridSearcher가 사용하는 모든 리트리버는 이 프로토콜을 준수해야 합니다.
    [EN] All retrievers used by HybridSearcher must conform to this protocol.
    """

    def search(
        self, query: str, k: int, metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        [KO] 검색을 수행하고 점수 내림차순으로 정렬된 결과 리스트를 반환합니다.
        [EN] Performs a search and returns a list of results sorted by score in descending order.

        [KO] 반환 리스트의 각 요소는 최소한 다음 필드를 포함해야 합니다:
        [EN] Each element in the returned list must contain at least the following fields:
        - content (str): [KO] 문서 내용 / [EN] Document content
        - metadata (dict): [KO] 관련 메타데이터 / [EN] Associated metadata
        - score (float): [KO] 검색 점수 (내림차순 정렬 가정) / [EN] Search score (assumed descending order)

        [KO] 참고: RRF는 절대 점수가 아닌 순위(Rank)를 기반으로 작동하지만,
        인터페이스 일관성을 위해 score 필드 포함을 권장합니다.
        [EN] Note: RRF operates on rank rather than absolute score, but including
        the score field is recommended for interface consistency.

        Args:
            query (str): [KO] 검색 질의 / [EN] Search query string
            k (int): [KO] 반환할 최대 결과 수 / [EN] Maximum number of results to return
            metadata_filter (Optional[Dict[str, Any]]): [KO] 메타데이터 필터 조건 (예: {"category": "Projects"})
                / [EN] Metadata filter conditions (e.g., {"category": "Projects"})

        Returns:
            List[Dict[str, Any]]: [KO] 검색 결과 딕셔너리의 리스트 (content, metadata, score 포함)
                / [EN] List of search result dictionaries (including content, metadata, score)
        """
        ...


class HybridSearcher:
    """
    [KO] FAISS(Dense)와 BM25(Sparse)의 결과를 RRF(Reciprocal Rank Fusion)로 병합하는 검색기.
    [EN] A searcher that merges results from FAISS (Dense) and BM25 (Sparse) using RRF (Reciprocal Rank Fusion).

    [KO] 계약 및 전제 조건:
    [EN] Contract and Preconditions:
    - [KO] 주입되는 리트리버는 `search` 메서드를 통해 점수 내림차순으로 정렬된 결과를 반환해야 합니다.
      [EN] The injected retrievers must return results sorted by score in descending order via the `search` method.
    - [KO] RRF는 절대 점수가 아닌 '순위(Rank)'만을 사용하여 병합하므로, 두 검색 엔진의 점수 스케일이
      달라도 안정적인 병합이 가능합니다.
      [EN] RRF merges results using only rank (not absolute score), enabling stable merging even
      when the two search engines have different score scales.
    """

    def __init__(
        self,
        faiss_retriever: Retriever,
        bm25_retriever: Retriever,
        rrf_k: int = 60,
    ):
        """
        [KO] 초기화: FAISS/BM25 리트리버를 주입하고 RRF 페널티 상수를 설정합니다.
        [EN] Initialization: Injects FAISS/BM25 retrievers and configures the RRF penalty constant.

        Args:
            faiss_retriever (Retriever): [KO] `search()` 메서드를 가진 Dense 벡터 리트리버
                / [EN] Dense vector retriever with a `search()` method
            bm25_retriever (Retriever): [KO] `search()` 메서드를 가진 Sparse 키워드 리트리버
                / [EN] Sparse keyword retriever with a `search()` method
            rrf_k (int): [KO] RRF 페널티 상수 (기본값: 60, 반드시 양수여야 함).
                값이 클수록 고순위 문서 간의 점수 차이가 완만해집니다.
                / [EN] RRF penalty constant (default: 60, must be positive).
                Larger values smooth out score differences between top-ranked documents.

        Raises:
            ValueError: [KO] rrf_k가 0 이하인 경우 / [EN] If rrf_k is not positive
        """
        if rrf_k <= 0:
            raise ValueError(f"rrf_k must be positive, got {rrf_k}")

        self.faiss_retriever = faiss_retriever
        self.bm25_retriever = bm25_retriever
        self.rrf_k = rrf_k

    def _get_doc_key(self, doc: Dict[str, Any]) -> str:
        """
        [KO] 문서 식별을 위한 고유 키를 생성합니다. (메타데이터 ID 우선, 없을 경우 SHA-256 해시)
        [EN] Generates a unique key for document identification. (Prefers metadata ID; falls back to SHA-256 hash)

        [KO] 동일 문서가 FAISS와 BM25 양쪽에서 반환될 때 중복 집계를 방지하기 위해 사용됩니다.
        [EN] Used to prevent duplicate aggregation when the same document is returned by both FAISS and BM25.

        Args:
            doc (Dict[str, Any]): [KO] 리트리버가 반환한 단일 검색 결과 딕셔너리
                / [EN] A single search result dictionary returned by a retriever

        Returns:
            str: [KO] 문서의 고유 식별자 (metadata["id"] 또는 SHA-256 해시)
                / [EN] Unique identifier for the document (metadata["id"] or SHA-256 hash)
        """
        metadata = doc.get("metadata")
        if isinstance(metadata, dict) and "id" in metadata:
            return str(metadata["id"])

        # [KO] ID가 없는 경우 내용과 메타데이터 정보를 조합해 해시 생성
        # [EN] If no ID exists, generate a hash by combining content and metadata fields
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
        filter_expansion_factor: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        [KO] 하이브리드 검색을 수행한 후 RRF 점수로 재정렬하여 반환합니다.
        [EN] Performs hybrid search and returns results re-ranked by RRF score.

        [KO] 내부 동작 순서:
        [EN] Internal execution flow:
        1. [KO] FAISS/BM25 각각에서 후보 문서를 검색합니다.
           [EN] Retrieve candidate documents from FAISS and BM25 independently.
        2. [KO] 각 결과의 순위(Rank)를 기반으로 RRF 점수를 계산하고 alpha 가중치를 적용합니다.
           [EN] Compute RRF scores based on the rank of each result and apply the alpha weight.
        3. [KO] 최종 RRF 점수를 기준으로 내림차순 정렬하여 상위 k개를 반환합니다.
           [EN] Sort in descending order by final RRF score and return the top-k results.

        Args:
            query (str): [KO] 검색 질의 / [EN] Search query string
            k (int): [KO] 최종 반환할 문서 수 (0 이상) / [EN] Number of final results to return (non-negative)
            faiss_k (Optional[int]): [KO] FAISS에서 가져올 후보 수 (기본값: k × filter_expansion_factor, 필터 시만 적용)
                / [EN] Number of candidates to fetch from FAISS (default: k × filter_expansion_factor, only when filtering)
            bm25_k (Optional[int]): [KO] BM25에서 가져올 후보 수 (기본값: k × filter_expansion_factor, 필터 시만 적용)
                / [EN] Number of candidates to fetch from BM25 (default: k × filter_expansion_factor, only when filtering)
            alpha (float): [KO] [0, 1] 범위의 Dense/Sparse 가중치. 1.0에 가까울수록 FAISS 비중이 커짐.
                / [EN] Dense/Sparse weight in [0, 1]. Values closer to 1.0 increase FAISS influence.
            metadata_filter (Optional[Dict[str, Any]]): [KO] 메타데이터 필터 조건 (예: {"category": "Projects"})
                / [EN] Metadata filter conditions (e.g., {"category": "Projects"})
            filter_expansion_factor (int): [KO] 후보군 확장 계수 (기본값: 2).
                metadata_filter가 제공되고 faiss_k/bm25_k가 None인 경우에만 적용됩니다.
                / [EN] Candidate expansion factor (default: 2).
                Applied only when metadata_filter is provided and faiss_k/bm25_k are None.

        Returns:
            List[Dict[str, Any]]: [KO] RRF 점수 기준 내림차순으로 정렬된 검색 결과 리스트
                (각 항목은 content, metadata, id, score 포함)
                / [EN] List of search results sorted by RRF score in descending order
                (each item includes content, metadata, id, score)

        Raises:
            ValueError: [KO] alpha가 [0, 1] 범위를 벗어나거나, k/faiss_k/bm25_k가 음수이거나,
                filter_expansion_factor가 1 미만인 경우
                / [EN] If alpha is out of [0, 1] range, k/faiss_k/bm25_k is negative,
                or filter_expansion_factor is less than 1
        """
        # [KO] 파라미터 유효 범위 검증
        # [EN] Validate parameter value ranges
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha must be between 0 and 1 (inclusive), got {alpha}")

        if k < 0:
            raise ValueError(f"k must be non-negative, got {k}")

        if k == 0:
            return []

        if filter_expansion_factor < 1:
            raise ValueError(
                f"filter_expansion_factor must be at least 1, got {filter_expansion_factor}"
            )

        # [KO] 개별 k 값에 대한 음수 검증
        # [EN] Validate that individual k values are non-negative
        if faiss_k is not None and faiss_k < 0:
            raise ValueError(f"faiss_k must be non-negative, got {faiss_k}")
        if bm25_k is not None and bm25_k < 0:
            raise ValueError(f"bm25_k must be non-negative, got {bm25_k}")

        # [KO] None 여부를 명시적으로 확인하여 0을 허용하고, 필터 유무에 따라 확장 계수를 선택적 적용
        # [EN] Explicitly check for None to allow 0, and selectively apply expansion factor based on filter presence
        actual_expansion = filter_expansion_factor if metadata_filter is not None else 1
        f_k = faiss_k if faiss_k is not None else (k * actual_expansion)
        b_k = bm25_k if bm25_k is not None else (k * actual_expansion)

        # [KO] 1. 각 검색 엔진에서 후보 문서 수집
        # [EN] 1. Collect candidate documents from each search engine
        faiss_results = self.faiss_retriever.search(
            query, k=f_k, metadata_filter=metadata_filter
        )
        bm25_results = self.bm25_retriever.search(
            query, k=b_k, metadata_filter=metadata_filter
        )

        # [KO] 2. RRF 점수 누적을 위한 딕셔너리 초기화
        # [EN] 2. Initialize dictionaries for RRF score accumulation
        rrf_scores: Dict[str, float] = {}
        merged_docs: Dict[str, Dict[str, Any]] = {}

        # [KO] FAISS 결과를 RRF에 반영 (가중치: alpha)
        # [EN] Apply FAISS results to RRF (weight: alpha)
        for rank, res in enumerate(faiss_results, 1):
            doc_key = self._get_doc_key(res)
            if doc_key not in rrf_scores:
                rrf_scores[doc_key] = 0.0
                merged_docs[doc_key] = {
                    "content": res.get("content", ""),
                    "metadata": res.get("metadata", {}),
                }
            rrf_scores[doc_key] += alpha * (1.0 / (self.rrf_k + rank))

        # [KO] BM25 결과를 RRF에 반영 (가중치: 1.0 - alpha)
        # [EN] Apply BM25 results to RRF (weight: 1.0 - alpha)
        for rank, res in enumerate(bm25_results, 1):
            doc_key = self._get_doc_key(res)
            if doc_key not in rrf_scores:
                rrf_scores[doc_key] = 0.0
                merged_docs[doc_key] = {
                    "content": res.get("content", ""),
                    "metadata": res.get("metadata", {}),
                }
            rrf_scores[doc_key] += (1.0 - alpha) * (1.0 / (self.rrf_k + rank))

        # [KO] 3. 최종 RRF 점수 기준 내림차순 정렬
        # [EN] 3. Sort in descending order by final RRF score
        sorted_keys = sorted(
            rrf_scores.keys(), key=lambda key: rrf_scores[key], reverse=True
        )

        final_results = []
        for doc_key in sorted_keys[:k]:
            doc_info = merged_docs[doc_key].copy()
            doc_info["id"] = (
                doc_key  # [KO] 고유 식별자 포함 / [EN] Include unique identifier
            )
            doc_info["score"] = rrf_scores[doc_key]
            final_results.append(doc_info)

        # [KO] 구조화된 로깅으로 검색 완료 기록
        # [EN] Record search completion with structured logging
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

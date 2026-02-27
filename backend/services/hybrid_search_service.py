# backend/services/hybrid_search_service.py

"""
하이브리드 검색 서비스 (Step 6: RAG API Integration)

리뷰 피드백 반영:
1. lru_cache를 이용한 Thread-safe 싱글톤 패턴 적용
2. PARACategory Enum 및 DTO(HybridSearchResult) 도입으로 타입 안전성 강화
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Any, List, Optional

from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever
from backend.hybrid_search import HybridSearcher
from backend.api.models import PARACategory

logger = logging.getLogger(__name__)


@dataclass
class HybridSearchResult:
    """
    하이브리드 검색 결과 DTO.
    서비스와 엔드포인트 간의 명확한 데이터 계약을 위해 사용합니다.
    """

    results: List[Dict[str, Any]]
    applied_filter: Optional[Dict[str, Any]]


class HybridSearchService:
    """
    HybridSearcher를 감싸는 서비스 클래스.
    """

    def __init__(
        self,
        *args: Any,
        rrf_k: int = 60,
        faiss_dimension: int = 1536,
        faiss_retriever: Optional[FAISSRetriever] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
        **kwargs: Any,
    ) -> None:
        """
        하위 호환성을 극대화한 하이브리드 검색 서비스 생성자.
        위치 인수(Positional Arguments)의 순서 변경에 따른 파괴적 변경을 방지하기 위해
        전달된 인자의 타입을 체크하여 지능적으로 할당합니다.
        """
        # 1. 초기값 설정
        self._rrf_k = rrf_k
        self._faiss_dim = faiss_dimension
        self._faiss_ret = faiss_retriever
        self._bm25_ret = bm25_retriever

        # 2. 위치 인수(*args) 처리 (과거 순서 조합 대응)
        # Case A: (rrf_k, dim, ret1, ret2)
        # Case B: (ret1, ret2, rrf_k, dim)
        for i, arg in enumerate(args):
            if i == 0:
                if isinstance(arg, int):
                    self._rrf_k = arg
                elif hasattr(arg, "search"):
                    self._faiss_ret = arg
            elif i == 1:
                if isinstance(arg, int):
                    self._faiss_dim = arg
                elif hasattr(arg, "search"):
                    self._bm25_ret = arg
            elif i == 2:
                if isinstance(arg, int):
                    self._rrf_k = arg  # 드문 케이스 대응
                elif hasattr(arg, "search"):
                    self._faiss_ret = arg
            elif i == 3:
                if hasattr(arg, "search"):
                    self._bm25_ret = arg

        # 3. 추가 키워드 인수(**kwargs) 처리 (하위 호환용)
        if "faiss_retriever" in kwargs:
            self._faiss_ret = kwargs["faiss_retriever"]
        if "bm25_retriever" in kwargs:
            self._bm25_ret = kwargs["bm25_retriever"]

        # 4. 인스턴스 할당 (명시적 None 체크 유지)
        self.faiss_retriever = (
            self._faiss_ret
            if self._faiss_ret is not None
            else FAISSRetriever(dimension=self._faiss_dim)
        )
        self.bm25_retriever = (
            self._bm25_ret if self._bm25_ret is not None else BM25Retriever()
        )

        # 5. 검색기 초기화
        self.searcher = HybridSearcher(
            faiss_retriever=self.faiss_retriever,
            bm25_retriever=self.bm25_retriever,
            rrf_k=self._rrf_k,
        )
        logger.info(
            "HybridSearchService initialized (rrf_k=%d, dim=%d, DI=%s)",
            self._rrf_k,
            self._faiss_dim,
            (
                "Yes"
                if (self._faiss_ret is not None or self._bm25_ret is not None)
                else "No"
            ),
        )

    # ------------------------------------------------------------------
    # 퍼블릭 메서드
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 5,
        alpha: float = 0.5,
        category: Optional[PARACategory] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> HybridSearchResult:
        """
        하이브리드 검색 수행 후 구조화된 DTO 객체로 반환.

        참고: 이 메서드는 CPU/IO bound 작업을 포함하므로
        FastAPI 엔드포인트에서 run_in_threadpool 등을 통해 비동기적으로 실행해야 합니다.
        """
        # 0. 서비스 레벨 파라미터 검증 (방어적 프로그래밍)
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be between 0.0 and 1.0, got {alpha}")
        if k < 1:
            raise ValueError(f"k must be greater than or equal to 1, got {k}")

        # 1. PARA 카테고리 검증 및 필터 병합
        effective_filter = self._build_metadata_filter(category, metadata_filter)

        logger.info(
            "Hybrid search call: query_len=%d, k=%d, alpha=%.2f, filter=%s",
            len(query),
            k,
            alpha,
            effective_filter,
        )

        # 2. 검색 실행
        raw_results = self.searcher.search(
            query=query,
            k=k,
            alpha=alpha,
            metadata_filter=effective_filter,
        )

        return HybridSearchResult(results=raw_results, applied_filter=effective_filter)

    def is_ready(self) -> bool:
        """인덱스에 문서가 있으면 True."""
        faiss_ready = self.faiss_retriever.size() > 0
        bm25_ready = len(self.bm25_retriever.documents) > 0
        return faiss_ready and bm25_ready

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _build_metadata_filter(
        category: Optional[PARACategory],
        extra_filter: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        PARA 카테고리와 추가 필터를 하나의 메타데이터 필터 딕셔너리로 병합.

        Raises:
            ValueError: extra_filter에 이미 다른 'category'가 존재하는 경우
        """
        merged: Dict[str, Any] = {}

        # 추가 필터 먼저 삽입
        if extra_filter:
            merged.update(extra_filter)

        # PARACategory Enum 값 삽입
        if category is not None:
            # [Review 반영] extra_filter에 이미 category가 존재하고 값이 다른 경우 충돌로 간주
            if "category" in merged and merged["category"] != category.value:
                raise ValueError(
                    f"Category conflict: extra_filter has '{merged['category']}' "
                    f"but explicit category is '{category.value}'."
                )
            merged["category"] = category.value

        return merged if merged else None


# ------------------------------------------------------------------
# 싱글톤 팩토리 (lru_cache를 사용하여 스레드 안전성 확보)
# ------------------------------------------------------------------


@lru_cache(maxsize=None)
def get_hybrid_search_service() -> HybridSearchService:
    """
    FastAPI Dependency Injection용 싱글톤 팩토리.
    @lru_cache(maxsize=None)을 사용하여 첫 호출 시에만 인스턴스를 생성하고 이후 재사용합니다.
    이 방식은 전역 초기화 레이스 컨디션을 방지하는 명시적이고 견고한 방법입니다.
    """
    logger.info("Creating HybridSearchService singleton instance...")
    return HybridSearchService()

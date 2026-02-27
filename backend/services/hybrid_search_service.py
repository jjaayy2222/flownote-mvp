# backend/services/hybrid_search_service.py

"""
하이브리드 검색 서비스 (Step 6: RAG API Integration)

FAISSRetriever와 BM25Retriever를 HybridSearcher와 연결하는
싱글톤 서비스 레이어. API 엔드포인트와 검색 엔진 사이의 의존성을 관리합니다.
"""

import logging
from typing import Dict, Any, List, Optional

from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever
from backend.hybrid_search import HybridSearcher
from backend.api.models import PARA_CATEGORIES

logger = logging.getLogger(__name__)


class HybridSearchService:
    """
    HybridSearcher를 감싸는 서비스 클래스.

    - FAISSRetriever / BM25Retriever를 초기화하여 HybridSearcher에 주입합니다.
    - PARA 카테고리 검증 및 메타데이터 필터 병합 로직을 담당합니다.
    - 호출 측(엔드포인트)은 이 클래스만 알면 됩니다.
    """

    def __init__(
        self,
        rrf_k: int = 60,
        faiss_dimension: int = 1536,
    ) -> None:
        """
        Args:
            rrf_k: RRF 페널티 상수 (기본값: 60)
            faiss_dimension: FAISS 임베딩 벡터 차원
        """
        self.faiss_retriever = FAISSRetriever(dimension=faiss_dimension)
        self.bm25_retriever = BM25Retriever()
        self.searcher = HybridSearcher(
            faiss_retriever=self.faiss_retriever,
            bm25_retriever=self.bm25_retriever,
            rrf_k=rrf_k,
        )
        logger.info(
            "HybridSearchService initialized (rrf_k=%d, dim=%d)", rrf_k, faiss_dimension
        )

    # ------------------------------------------------------------------
    # 퍼블릭 메서드
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 5,
        alpha: float = 0.5,
        category: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        하이브리드 검색 수행 후 API 응답 형식으로 반환.

        Args:
            query: 검색 질의
            k: 반환할 결과 수
            alpha: Dense(FAISS) 가중치 [0.0, 1.0]
            category: PARA 카테고리 필터 (문자열, 선택)
            metadata_filter: 추가 메타데이터 필터 (선택)

        Returns:
            dict with keys: results, applied_filter
        """
        # 1. PARA 카테고리 검증 및 필터 병합
        effective_filter = self._build_metadata_filter(category, metadata_filter)

        logger.info(
            "Hybrid search request: query_len=%d, k=%d, alpha=%.2f, filter=%s",
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

        return {
            "results": raw_results,
            "applied_filter": effective_filter,
        }

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
        category: Optional[str],
        extra_filter: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        PARA 카테고리와 추가 필터를 하나의 메타데이터 필터 딕셔너리로 병합.

        Args:
            category: PARA 카테고리 문자열 (검증 후 필터에 추가)
            extra_filter: 사용자 제공 추가 메타데이터 필터

        Returns:
            병합된 필터 딕셔너리 또는 None (필터 없음)

        Raises:
            ValueError: 지원하지 않는 PARA 카테고리가 전달된 경우
        """
        merged: Dict[str, Any] = {}

        # 추가 필터 먼저 삽입
        if extra_filter:
            merged.update(extra_filter)

        # PARA 카테고리 검증 및 삽입
        if category is not None:
            if category not in PARA_CATEGORIES:
                raise ValueError(
                    f"지원하지 않는 카테고리: '{category}'. "
                    f"허용값: {PARA_CATEGORIES}"
                )
            merged["category"] = category

        return merged if merged else None


# ------------------------------------------------------------------
# 싱글톤 인스턴스 (애플리케이션 전체에서 공유)
# ------------------------------------------------------------------

_service_instance: Optional[HybridSearchService] = None


def get_hybrid_search_service() -> HybridSearchService:
    """
    FastAPI Dependency Injection용 싱글톤 팩토리.

    Returns:
        HybridSearchService 인스턴스
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = HybridSearchService()
        logger.info("HybridSearchService singleton created.")
    return _service_instance

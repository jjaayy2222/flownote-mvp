# backend/api/endpoints/search.py

"""
하이브리드 검색 엔드포인트 (Step 6: RAG API Integration)

리뷰 피드백 반영:
1. run_in_threadpool을 사용하여 CPU/IO 바운드 검색 작업의 비차단 실행 보장
2. HybridSearchResult DTO 연동
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool

from backend.api.deps import get_locale
from backend.api.models import (
    SearchResponse,
    HybridSearchRequest,
    HybridSearchResponse,
    SearchResultItem,
    PARACategory,
)
from backend.services.hybrid_search_service import (
    HybridSearchService,
    get_hybrid_search_service,
)
from backend.services.i18n_service import get_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 기존 엔드포인트 (하위 호환 유지)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/", response_model=SearchResponse, summary="기본 검색 (하위 호환)")
async def search_files(
    q: str,
    locale: str = Depends(get_locale),
) -> SearchResponse:
    """기존 검색 엔드포인트 (하위 호환 유지).

    현재는 빈 결과를 반환합니다. RAG 검색은 /search/hybrid를 사용하세요.
    """
    results = []
    return SearchResponse(
        status="success",
        message=get_message("search_results", locale, count=len(results)),
        query=q,
        results=results,
        count=len(results),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 하이브리드 RAG 검색 엔드포인트 (신규)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post(
    "/hybrid",
    # response_model_exclude_none=True,  # None 필드 제외 옵션 (필요 시)
    response_model=HybridSearchResponse,
    summary="하이브리드 RAG 검색 (POST)",
    description=(
        "FAISS(Dense) + BM25(Sparse) 하이브리드 검색을 수행하고 "
        "RRF(Reciprocal Rank Fusion) 알고리즘으로 결과를 병합합니다.\n\n"
        "**PARA 카테고리 필터**: `category` 필드로 Projects / Areas / Resources / Archives 중 하나를 지정할 수 있습니다."
    ),
)
async def hybrid_search_post(
    request: HybridSearchRequest,
    service: HybridSearchService = Depends(get_hybrid_search_service),
) -> HybridSearchResponse:
    """JSON Body로 검색 요청을 전달하는 하이브리드 RAG 검색."""
    return await _run_hybrid_search(
        service=service,
        query=request.query,
        k=request.k,
        alpha=request.alpha,
        category=request.category,
        metadata_filter=request.metadata_filter,
    )


@router.get(
    "/hybrid",
    response_model=HybridSearchResponse,
    summary="하이브리드 RAG 검색 (GET)",
    description=(
        "쿼리 파라미터를 사용하는 간편 하이브리드 RAG 검색.\n\n"
        "예: `GET /search/hybrid?q=프로젝트+일정&k=5&category=Projects`"
    ),
)
async def hybrid_search_get(
    q: str = Query(..., min_length=1, description="검색 질의"),
    k: int = Query(default=5, ge=1, le=50, description="반환할 결과 수 (1~50)"),
    alpha: float = Query(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Dense 검색 가중치 (0.0=BM25 전용, 1.0=FAISS 전용)",
    ),
    category: Optional[PARACategory] = Query(
        default=None,
        description="PARA 카테고리 필터 (Projects, Areas, Resources, Archives)",
    ),
    service: HybridSearchService = Depends(get_hybrid_search_service),
) -> HybridSearchResponse:
    """쿼리 파라미터를 사용하는 간편 하이브리드 RAG 검색."""
    return await _run_hybrid_search(
        service=service,
        query=q,
        k=k,
        alpha=alpha,
        category=category,
        metadata_filter=None,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 내부 헬퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def _run_hybrid_search(
    service: HybridSearchService,
    query: str,
    k: int,
    alpha: float,
    category: Optional[PARACategory],
    metadata_filter: Optional[dict],
) -> HybridSearchResponse:
    """POST/GET 공통 검색 실행 로직."""
    try:
        # [Performance] service.search는 동기 메서드(FAISS/BM25)이므로
        # run_in_threadpool을 사용하여 메인 이벤트 루프 블로킹 방지
        result = await run_in_threadpool(
            service.search,
            query=query,
            k=k,
            alpha=alpha,
            category=category,
            metadata_filter=metadata_filter,
        )
    except ValueError as exc:
        # PARA 카테고리 유효성 오류 등
        logger.warning("Hybrid search validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Hybrid search unexpected error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="검색 중 내부 오류가 발생했습니다.",
        ) from exc

    # DTO 속성 접근
    raw_results = result.results
    applied_filter = result.applied_filter

    # 결과 직렬화 (SearchResultItem)
    items = [
        SearchResultItem(
            content=doc.get("content", ""),
            metadata=doc.get("metadata", {}),
            score=doc.get("score", 0.0),
        )
        for doc in raw_results
    ]

    logger.info(
        "Hybrid search completed: query_len=%d, returned=%d, filter=%s",
        len(query),
        len(items),
        applied_filter,
    )

    return HybridSearchResponse(
        status="success",
        query=query,
        results=items,
        count=len(items),
        alpha=alpha,
        applied_filter=applied_filter,
    )

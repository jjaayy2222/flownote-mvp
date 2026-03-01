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
from backend.hybrid_search import HybridSearcher, Retriever
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


# 기본값 감지를 위한 센티넬 객체
_DEFAULT = object()


class HybridSearchService:
    """
    HybridSearcher를 감싸는 서비스 클래스.
    """

    # 하위 호환성 및 테스트 정합성을 위한 기본값 상수
    DEFAULT_RRF_K = 60
    DEFAULT_FAISS_DIMENSION = 1536

    # 위치 인수 매핑 규칙 (리뷰 제안: 테이블 기반 접근)
    # 인덱스별로 (타입, 타겟 키) 리스트 정의
    _POSITION_RULES = {
        0: [(int, "rrf_k"), (Retriever, "faiss_ret")],
        1: [(int, "faiss_dim"), (Retriever, "bm25_ret")],
        2: [(int, "rrf_k"), (Retriever, "faiss_ret")],
        3: [(int, "faiss_dim"), (Retriever, "bm25_ret")],
    }

    def __init__(
        self,
        *args: Any,
        rrf_k: int = DEFAULT_RRF_K,
        faiss_dimension: int = DEFAULT_FAISS_DIMENSION,
        faiss_retriever: Optional[FAISSRetriever] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
        **kwargs: Any,
    ) -> None:
        """
        하위 호환성을 보장하는 지능형 생성자.

        상위 브랜치 리뷰 반영:
        1. 상수(DEFAULT_*)를 사용하여 기본값 관리 일원화.
        2. 명시적인 타입 체크(FAISSRetriever, BM25Retriever) 적용.
        3. 위치/키워드 충돌 및 우선순위 정책 명확화.
        """
        # Python의 인자 바인딩 특성상, rrf_k=... 등은 이미 해당 변수에 할당됨.
        # 위치 인수는 args로 들어옴.
        resolved = self._resolve_init_args(
            args,
            kwargs,
            rrf_k=rrf_k,
            faiss_dim=faiss_dimension,
            faiss_ret=faiss_retriever,
            bm25_ret=bm25_retriever,
        )

        self.faiss_retriever = resolved["faiss_ret"]
        self.bm25_retriever = resolved["bm25_ret"]
        self.is_di = resolved["is_di"]
        self._resolved_params = resolved  # 디버깅용

        # 통합 검색기 초기화
        self.searcher = HybridSearcher(
            faiss_retriever=self.faiss_retriever,
            bm25_retriever=self.bm25_retriever,
            rrf_k=resolved["rrf_k"],
        )
        logger.info(
            "HybridSearchService initialized (rrf_k=%d, dim=%d, DI=%s)",
            resolved["rrf_k"],
            resolved["faiss_dim"],
            "Yes" if self.is_di else "No",
        )

    def _resolve_init_args(
        self,
        args: tuple,
        kwargs: Dict[str, Any],
        rrf_k: int,
        faiss_dim: int,
        faiss_ret: Optional[Retriever],
        bm25_ret: Optional[Retriever],
    ) -> Dict[str, Any]:
        """위치 인수와 키워드 인수를 병합하고 우선순위를 결정하는 헬퍼."""
        # 1. 시그니처에 의해 자동으로 바인딩된 값들로 시작
        res = {
            "rrf_k": rrf_k,
            "faiss_dim": faiss_dim,
            "faiss_ret": faiss_ret,
            "bm25_ret": bm25_ret,
        }

        # 2. **kwargs에 별칭이나 명시되지 않은 키워드가 있는 경우 처리
        if "rrf_k_alias" in kwargs:
            res["rrf_k"] = kwargs["rrf_k_alias"]

        # 3. 위치 인수(*args) 처리 (테스트 및 레거시 대응)
        for i, arg in enumerate(args):
            rules = self._POSITION_RULES.get(i)
            if not rules:
                # [Review 반영] 허용 가능한 최대 위치 인자 수를 _POSITION_RULES에서 유동적으로 계산
                max_pos = len(self._POSITION_RULES)
                raise TypeError(
                    f"HybridSearchService() takes up to {max_pos} positional arguments but {len(args)} were given"
                )

            target_key = None
            for expected_type, key in rules:
                if isinstance(arg, expected_type):
                    target_key = key
                    break

            if target_key:
                current_val = res[target_key]
                # 명시적 키워드 우선순위 체크 (헬퍼 메서드 분리)
                if self._is_overridden_by_keyword(target_key, current_val, arg):
                    logger.warning(
                        "Positional argument at index %d ignored in favor of explicit keyword argument",
                        i,
                    )
                    continue

                res[target_key] = arg
            else:
                # 타입 매칭 실패 시 경고 (또는 에러)
                logger.warning(
                    "Positional argument at index %d (%s) did not match any expected types",
                    i,
                    type(arg).__name__,
                )

        # 4. 최종 할당 및 None 체크
        final_faiss = (
            res["faiss_ret"]
            if res["faiss_ret"] is not None
            else FAISSRetriever(dimension=res["faiss_dim"])
        )
        final_bm25 = res["bm25_ret"] if res["bm25_ret"] is not None else BM25Retriever()

        return {
            "rrf_k": res["rrf_k"],
            "faiss_dim": res["faiss_dim"],
            "faiss_ret": final_faiss,
            "bm25_ret": final_bm25,
            "is_di": (res["faiss_ret"] is not None or res["bm25_ret"] is not None),
        }

    def _is_overridden_by_keyword(
        self, key: str, current_val: Any, new_val: Any
    ) -> bool:
        """키워드 인수가 기본값이 아닌 명시적인 값인지 판별하는 헬퍼."""
        # 명시적인 키 목록과 기본값 체크 정책 (리뷰 반영: Allowlist & Robustness)
        if key == "rrf_k":
            is_explicit = current_val != self.DEFAULT_RRF_K
        elif key == "faiss_dim":
            is_explicit = current_val != self.DEFAULT_FAISS_DIMENSION
        elif key in ("faiss_ret", "bm25_ret"):
            # 리트리버는 None이 아니면 명시적 주입으로 간주
            is_explicit = current_val is not None
        else:
            # 알 수 없는 키가 들어온 경우, 내부 로직 오류이므로 개발 환경에서 검지할 수 있도록 assert 사용.
            # 런타임 환경(-O)에서는 무시되며 기본적으로 '명시적이지 않음'으로 간주하여 호환성 유지.
            assert key in (
                "rrf_k",
                "faiss_dim",
                "faiss_ret",
                "bm25_ret",
            ), f"Missing mapping for parameter key: {key}"
            return False

        return is_explicit and current_val != new_val

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
        filter_expansion_factor: int = 2,
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
        if filter_expansion_factor < 1:
            raise ValueError(
                f"filter_expansion_factor must be at least 1, got {filter_expansion_factor}"
            )

        # 1. PARA 카테고리 검증 및 필터 병합
        effective_filter = self._build_metadata_filter(category, metadata_filter)

        logger.info(
            "Hybrid search call: query_len=%d, k=%d, alpha=%.2f, filter=%s, expansion=%d",
            len(query),
            k,
            alpha,
            effective_filter,
            filter_expansion_factor,
        )

        # 2. 검색 실행
        raw_results = self.searcher.search(
            query=query,
            k=k,
            alpha=alpha,
            metadata_filter=effective_filter,
            filter_expansion_factor=filter_expansion_factor,
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

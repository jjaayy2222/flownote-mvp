# backend/services/hybrid_search_service.py

"""
하이브리드 검색 서비스 (Step 6: RAG API Integration)

리뷰 피드백 반영:
1. lru_cache를 이용한 Thread-safe 싱글톤 패턴 적용
2. PARACategory Enum 및 DTO(HybridSearchResult) 도입으로 타입 안전성 강화
"""

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Any, List, Optional

from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever
from backend.hybrid_search import HybridSearcher, Retriever
from backend.api.models import PARACategory
from backend.services.search_cache_service import search_cache_service
from fastapi.concurrency import run_in_threadpool

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

    # 하위 호환성 및 테스트 정합성을 위한 기본값 상수 (Single Source of Truth)
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

        # [Persistence] 앱 시작 시 자동 로드 시도 (DI가 아닌 경우에만)
        if not self.is_di:
            self.load_indices()

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
                logger.debug(
                    "Arg %d: %s -> %s (current: %s)", i, arg, target_key, current_val
                )
                # 명시적 키워드 우선순위 체크 (헬퍼 메서드 분리)
                if self._is_overridden_by_keyword(target_key, current_val, arg):
                    logger.warning(
                        "Positional argument at index %d ignored in favor of explicit keyword argument",
                        i,
                    )
                    continue

                res[target_key] = arg
                logger.debug("Updated %s to %s", target_key, arg)
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

    async def search(
        self,
        query: str,
        k: int = 5,
        alpha: float = 0.5,
        category: Optional[PARACategory] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        filter_expansion_factor: int = 2,
    ) -> HybridSearchResult:
        """
        하이브리드 검색 수행 (캐싱 레이어 포함).
        - Redis 캐시를 먼저 확인하고, 미스 시 실제 검색 수행.
        - 실제 검색은 CPU-bound 이므로 threadpool에서 실행.

        [Fail Fast 정책] 파라미터 검증은 이 public 진입점에서만 수행합니다.
        _execute_search는 이 메서드를 통해서만 호출되므로 중복 검증이 불필요합니다.
        """
        # [Fail Fast] 캐시 접근 전 파라미터 유효 범위 검증 (단일 검증 지점)
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be between 0.0 and 1.0, got {alpha}")
        if k < 1:
            raise ValueError(f"k must be greater than or equal to 1, got {k}")

        # 0. PARA 카테고리 검증 및 필터 병합
        effective_filter = self._build_metadata_filter(category, metadata_filter)

        # 1. Redis 캐시 확인 (Async)
        # [Review 반영] None 체크를 명시적으로 하여 빈 결과 세트([])가 캐시된 경우를 미스와 구분
        # [Review 반영] filter_expansion_factor를 캐시 키에 포함 (다른 expansion 값 → 다른 결과)
        cached_raw = await search_cache_service.get_results(
            query, k, alpha, effective_filter, filter_expansion_factor
        )
        if cached_raw is not None:
            return HybridSearchResult(
                results=cached_raw, applied_filter=effective_filter
            )

        # 2. 캐시 미스 시 실제 검색 실행 (Threadpool)
        result = await run_in_threadpool(
            self._execute_search,
            query=query,
            k=k,
            alpha=alpha,
            metadata_filter=effective_filter,
            filter_expansion_factor=filter_expansion_factor,
        )

        # 3. 결과 캐시에 저장 (Async, Background)
        # [Review 반영] filter_expansion_factor를 캐시 키 생성에 포함
        await search_cache_service.set_results(
            query, k, alpha, effective_filter, filter_expansion_factor, result.results
        )

        return result

    def _execute_search(
        self,
        query: str,
        k: int,
        alpha: float,
        metadata_filter: Optional[Dict[str, Any]],
        filter_expansion_factor: int = 2,
    ) -> HybridSearchResult:
        """실제 검색 로직 (CPU-bound).

        주의: 파라미터 검증은 public 진입점인 search()에서만 수행됩니다.
        이 메서드는 search()를 통해서만 호출되므로, 중복 검증을 포함하지 않습니다.
        """
        logger.info(
            "Executing Hybrid search: query_len=%d, k=%d, alpha=%.2f, filter_keys=%s, expansion=%d",
            len(query),
            k,
            alpha,
            list(metadata_filter.keys()) if metadata_filter else None,
            filter_expansion_factor,
        )

        raw_results = self.searcher.search(
            query=query,
            k=k,
            alpha=alpha,
            metadata_filter=metadata_filter,
            filter_expansion_factor=filter_expansion_factor,
        )

        return HybridSearchResult(results=raw_results, applied_filter=metadata_filter)

    def save_indices(self):
        """FAISS와 BM25 인덱스를 디스크에 저장"""
        from backend.config import PathConfig

        faiss_dir = PathConfig.FAISS_INDEX_DIR / "faiss"
        bm25_dir = PathConfig.FAISS_INDEX_DIR / "bm25"

        self.faiss_retriever.save(faiss_dir)
        self.bm25_retriever.save(bm25_dir)
        logger.info("✅ All search indices saved to disk.")

    def load_indices(self) -> bool:
        """디스크에서 FAISS와 BM25 인덱스 로드.

        Returns:
            True: 인덱스를 성공적으로 로드함.
            False: 인덱스 파일이 없거나 로드 불가능한 경우 (빈 인덱스로 시작).

        [Review 반영] 예외 처리 구체화:
        - FileNotFoundError: 초기 실행 등 정상 케이스 → INFO 로그 후 빈 인덱스로 시작.
        - (OS/IO) OSError, IOError: 파일 권한·디스크 오류 → WARNING 로그 후 빈 인덱스로 시작.
        - (역직렬화) Exception: pickle UnpicklingError 등 손상 파일 → ERROR 로그 후 빈 인덱스로 시작.
          서비스 시작 자체를 막지 않되, 로그로 명확히 인지할 수 있도록 합니다.
        """
        from backend.config import PathConfig

        faiss_dir = PathConfig.FAISS_INDEX_DIR / "faiss"
        bm25_dir = PathConfig.FAISS_INDEX_DIR / "bm25"

        try:
            self.faiss_retriever.load(faiss_dir)
            self.bm25_retriever.load(bm25_dir)
            logger.info("✅ All search indices loaded from disk.")
            return True
        except FileNotFoundError:
            # 정상 케이스: 최초 실행이거나 아직 저장된 인덱스가 없음
            logger.info("No search indices found on disk. Starting with empty indices.")
        except OSError as e:
            # 파일 권한 문제, 디스크 I/O 오류 등
            logger.warning(
                "I/O error while loading search indices (starting with empty indices): %s",
                e,
            )
        except Exception as e:
            # Pickle UnpicklingError, 버전 불일치 등 역직렬화 오류
            logger.error(
                "Failed to deserialize search indices; starting with empty indices. "
                "This may indicate corrupted or incompatible index files. error_type=%s",
                type(e).__name__,
                exc_info=True,
            )
        return False

    def is_ready(self) -> bool:
        """인덱스에 문서가 있으면 True."""
        faiss_ready = self.faiss_retriever.size() > 0
        bm25_ready = len(self.bm25_retriever.documents) > 0
        return faiss_ready and bm25_ready

    def determine_alpha(self, query: str) -> float:
        """
        질의의 언어적 특성을 분석하여 최적의 RRF alpha 값을 추천합니다.

        [Optimization Logic]
        1. Semantic-Rich (High Alpha): 자연어 문장, 질문형 어미, 추상적 용어 포함 시 FAISS 비중 확대.
        2. Keyword-Dense (Low Alpha): 따옴표, 날짜, 고유 코드, 짧은 단어 패턴 포함 시 BM25 비중 확대.
        """
        if not query or not query.strip():
            return 0.5

        # A. Semantic Bias (Dense 우선)
        # 구어체 문장, 의문사, "의미", "방법" 등을 묻는 패턴
        semantic_patterns = [
            r"(어떻게|방법|이유|왜|설명|알려|정리|해줘|뭐야|란|무엇|인가요|나 요|있나요)",
            r"(의미|뜻|차이|비교|특징)",
        ]
        if any(re.search(p, query) for p in semantic_patterns):
            return 0.7

        # B. Keyword Bias (Sparse 우선)
        # 따옴표로 감싸진 용어, 날짜 형식(YYYY-MM), 버전(v1.0), 특정 코드(ID-123)
        keyword_patterns = [
            r"([\"']).*?\1",  # 따옴표
            r"\d{4}[-./]\d{2}",  # 날짜형
            r"v\d+\.\d+",  # 버전형
            r"(\w+-\d+)",  # 코드형 (예: ISS-614)
        ]
        if any(re.search(p, query) for p in keyword_patterns):
            return 0.3

        # C. Default: 중립
        return 0.5

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

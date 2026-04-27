# backend/services/hybrid_search_service.py

"""
하이브리드 검색 서비스 (Step 6: RAG API Integration)

리뷰 피드백 반영:
1. lru_cache를 이용한 Thread-safe 싱글톤 패턴 적용
2. PARACategory Enum 및 DTO(HybridSearchResult) 도입으로 타입 안전성 강화

[Step 2-3 - Phase 2.3] 개인화 컨텍스트 가중치 라우팅
  - 1단계: 가중치 설정 레이어 (Configuration Layer)
    - 환경 변수 기반 개인화/전역 인덱스 혼합 비율 설정 (하드코딩 금지)
    - Cold Start 연동 단락(Short-circuit) 가중치 결정 함수 제공
    - PII-마스킹 로그 및 범위 Clamp(0.0~1.0) 포함

설계 원칙 (개인정보 보호 우선):
  - user_id는 절대 로그에 평문으로 기록하지 않는다.
  - 로그에 user_id를 출력해야 하는 경우 반드시 mask_pii_id() 헬퍼를 사용한다.
"""

import asyncio
import logging
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Any, List, Optional, Tuple

from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever
from backend.hybrid_search import HybridSearcher, Retriever
from backend.api.models import PARACategory
from backend.services.search_cache_service import search_cache_service
from backend.services import topic_clustering_service  # type: ignore[import]
from backend.utils.common import mask_pii_id, safe_parse_env_float  # type: ignore[import]
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

# [리뷰반영] 하드코딩 제거: 로깅 타임아웃을 환경 변수에서 가져오도록 설정 (기본값 3.0초)
# [리뷰반영] import 시점 크래시 방지: safe_parse_env_float 헬퍼를 사용하여 비정상 값 방어 및 0.1초 이상 강제
_LOG_SEARCH_HISTORY_TIMEOUT = safe_parse_env_float("SEARCH_HISTORY_LOG_TIMEOUT", 3.0, min_val=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# [Step 2-3 / Phase 2.3] 1단계: 가중치 설정 레이어 (Configuration Layer)
# ─────────────────────────────────────────────────────────────────────────────

# 개인화 인덱스 가중치 환경 변수 (하드코딩 금지 — 모두 여기서 중앙 관리)
_PERSONALIZED_WEIGHT_ENV_KEY = "PERSONALIZED_INDEX_WEIGHT"
_PERSONALIZED_WEIGHT_DEFAULT = 0.6
_PERSONALIZED_WEIGHT_MIN = 0.0
_PERSONALIZED_WEIGHT_MAX = 1.0

# 전역 인덱스 가중치 환경 변수
_GLOBAL_WEIGHT_ENV_KEY = "GLOBAL_INDEX_WEIGHT"
_GLOBAL_WEIGHT_DEFAULT = 0.4
_GLOBAL_WEIGHT_MIN = 0.0
_GLOBAL_WEIGHT_MAX = 1.0

# Cold Start 시 전역 인덱스 100% 편향
_COLD_START_PERSONALIZED_WEIGHT = 0.0
_COLD_START_GLOBAL_WEIGHT = 1.0

# 합산 보정 수치 상수 (하드코딩 금지 — 이곳에서만 수정)
# 합계가 이 값 미만이면 ZeroDivision 위험으로 간주하여 기본값으로 폴백
_WEIGHT_SUM_ZERO_EPSILON: float = 1e-9
# 합계가 1.0과 이 절댓값 이상 차이나면 재정규화를 수행한다.
# rel_tol(_WEIGHT_SUM_ZERO_EPSILON)과 달리 abs_tol을 사용하여
# "1.0 근처에서 얼마나 벗어났는가"를 예측 가능하게 판단한다.
_WEIGHT_SUM_NORMALIZATION_TOLERANCE: float = 1e-6
# 재정규화된 가중치를 반올림할 소수점 자리수 (6자리 ≈ 마이크로 단위 정밀도)
_WEIGHT_NORMALIZATION_PRECISION: int = 6


def _parse_bounded_weight(env_key: str, default: float, min_val: float, max_val: float) -> float:
    """
    가중치 환경 변수를 안전하게 파싱하고 [min_val, max_val] 범위로 Clamp하는 헬퍼.

    동작 우선순위:
      1) 미설정(None)       → 조용히 기본값 반환
      2) 빈값/공백         → 운영자 오설정 의심 → WARNING + 기본값
      3) 파싱 실패         → WARNING + 기본값
      4) 비정상 부동소수점  → NaN·±inf → WARNING + 기본값
      5) 범위 이탈         → Clamp + WARNING
      6) 정상             → 파싱된 값 반환
    """
    raw = os.environ.get(env_key)

    # 1) 미설정: 조용히 기본값 사용
    if raw is None:
        return default

    # 2) 빈값/공백: 운영자 오설정 의심
    stripped = raw.strip()
    if not stripped:
        logger.warning(
            "[HYBRID_SEARCH] %s 가 설정됐으나 빈값/공백입니다 (운영자 오설정 의심). "
            "기본값 %r로 폴백합니다.",
            env_key,
            default,
        )
        return default

    # 3) 파싱 실패
    try:
        value = float(stripped)
    except (ValueError, TypeError):
        logger.warning(
            "[HYBRID_SEARCH] %s 파싱 실패 (값=%r). 기본값 %r로 폴백합니다.",
            env_key,
            stripped,
            default,
        )
        return default

    # 4) 비정상 부동소수점 (NaN·±inf)
    if not math.isfinite(value):
        logger.warning(
            "[HYBRID_SEARCH] %s 값이 비정상 부동소수점(NaN 또는 ±inf)입니다 (운영자 오설정 의심). "
            "기본값 %r로 폴백합니다.",
            env_key,
            default,
        )
        return default

    # 5) 범위 Clamp
    if value < min_val:
        logger.warning(
            "[HYBRID_SEARCH] %s=%r 가 최솟값(%r) 미만입니다. %r로 보정합니다.",
            env_key, value, min_val, min_val,
        )
        return min_val

    if value > max_val:
        logger.warning(
            "[HYBRID_SEARCH] %s=%r 가 최댓값(%r) 초과입니다. %r로 보정합니다.",
            env_key, value, max_val, max_val,
        )
        return max_val

    return value


def _load_index_weights() -> Tuple[float, float]:
    """
    환경 변수에서 개인화/전역 인덱스 가중치를 로드하고 합산 보정(재정규화)을 수행한다.

    합산 보정 정책:
      - 두 가중치의 합이 0에 가까운 경우: 기본값(0.6 / 0.4)으로 폴백 (ZeroDivision 방지)
      - 두 가중치의 합이 1.0이 아닌 경우: 합계로 나눠 재정규화하고 WARNING 로그 기록
    """
    personalized = _parse_bounded_weight(
        _PERSONALIZED_WEIGHT_ENV_KEY,
        _PERSONALIZED_WEIGHT_DEFAULT,
        _PERSONALIZED_WEIGHT_MIN,
        _PERSONALIZED_WEIGHT_MAX,
    )
    global_w = _parse_bounded_weight(
        _GLOBAL_WEIGHT_ENV_KEY,
        _GLOBAL_WEIGHT_DEFAULT,
        _GLOBAL_WEIGHT_MIN,
        _GLOBAL_WEIGHT_MAX,
    )

    total = personalized + global_w

    # 합산이 0에 가까운 경우 (ZeroDivision 방지): 기본값으로 폴백
    if total < _WEIGHT_SUM_ZERO_EPSILON:
        logger.warning(
            "[HYBRID_SEARCH] %s + %s 의 합계가 0에 가깝습니다 (운영자 오설정 의심). "
            "기본값 (%.1f / %.1f)으로 폴백합니다.",
            _PERSONALIZED_WEIGHT_ENV_KEY,
            _GLOBAL_WEIGHT_ENV_KEY,
            _PERSONALIZED_WEIGHT_DEFAULT,
            _GLOBAL_WEIGHT_DEFAULT,
        )
        return _PERSONALIZED_WEIGHT_DEFAULT, _GLOBAL_WEIGHT_DEFAULT

    # abs_tol 전용 판단: "1.0 근처에서 절대 오차만으로 판단"
    # rel_tol=0.0 명시로 기본값(1e-9)의 암묵적 적용을 차단 → 주석과 코드 완전 일치
    # (rel_tol=_WEIGHT_SUM_ZERO_EPSILON은 ZeroDivision 가드 전용 개념과 분리)
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=_WEIGHT_SUM_NORMALIZATION_TOLERANCE):
        normalized_p = round(personalized / total, _WEIGHT_NORMALIZATION_PRECISION)
        normalized_g = round(global_w / total, _WEIGHT_NORMALIZATION_PRECISION)
        logger.warning(
            "[HYBRID_SEARCH] %s=%.4f + %s=%.4f 의 합계가 1.0이 아닙니다 (합계=%.4f). "
            "재정규화합니다: personalized=%.4f, global=%.4f.",
            _PERSONALIZED_WEIGHT_ENV_KEY, personalized,
            _GLOBAL_WEIGHT_ENV_KEY, global_w,
            total,
            normalized_p, normalized_g,
        )
        return normalized_p, normalized_g

    return personalized, global_w


# 모듈 로드 시 1회 계산 (런타임 환경 변수 변경은 재시작 또는 reload_index_weights() 호출로 반영)
_PERSONALIZED_INDEX_WEIGHT: float
_GLOBAL_INDEX_WEIGHT: float
_PERSONALIZED_INDEX_WEIGHT, _GLOBAL_INDEX_WEIGHT = _load_index_weights()


def reload_index_weights() -> Tuple[float, float]:
    """
    환경 변수에서 가중치를 다시 로드하여 모듈 레벨 싱글톤을 갱신한다.

    주주의 대상: 장수명 워커(Celery, 초로드 프로세스) 또는 운영 중 실험(A/B 테스트)에서
    프로세스 재시작 없이 약치를 적용할 때.

    동작 계약:
      - PERSONALIZED_INDEX_WEIGHT / GLOBAL_INDEX_WEIGHT 환경 변수를 읽어 Clamp + 합산 보정 수행
      - 모듈 레벨 _PERSONALIZED_INDEX_WEIGHT, _GLOBAL_INDEX_WEIGHT를 원자적으로 덧써 쓰기(global)
      - 갱신된 값을 튜플로 반환하여 호출자가 증거 로깅 가능

    Returns:
        갱신 후 (personalized_weight, global_weight) 튜플
    """
    global _PERSONALIZED_INDEX_WEIGHT, _GLOBAL_INDEX_WEIGHT
    _PERSONALIZED_INDEX_WEIGHT, _GLOBAL_INDEX_WEIGHT = _load_index_weights()
    logger.info(
        "[HYBRID_SEARCH][WEIGHT] 가중치 통신(reload) 완료: personalized=%.4f, global=%.4f",
        _PERSONALIZED_INDEX_WEIGHT,
        _GLOBAL_INDEX_WEIGHT,
    )
    return _PERSONALIZED_INDEX_WEIGHT, _GLOBAL_INDEX_WEIGHT


async def get_index_weights(hashed_user_id: str) -> Tuple[float, float]:
    """
    현재 사용자에게 적용할 (개인화 가중치, 전역 가중치) 튜플을 반환한다.

    Cold Start 판별 결과에 따라 즉시 전역 100% 편향으로 단락(Short-circuit)한다.
    이 함수는 2단계 라우터와 3단계 RRF 병합의 SSOT(Single Source of Truth)이다.

    Args:
        hashed_user_id: SHA-256 해시된 사용자 식별자 (평문 user_id 금지)

    Returns:
        (personalized_weight, global_weight) 튜플
        - Cold Start: (0.0, 1.0)
        - 정상 사용자: (_PERSONALIZED_INDEX_WEIGHT, _GLOBAL_INDEX_WEIGHT)
    """
    masked_uid = mask_pii_id(hashed_user_id)

    # Cold Start 판별 (topic_clustering_service SSOT 참조)
    is_cold = await topic_clustering_service.is_cold_start_user(
        hashed_user_id, masked_uid=masked_uid
    )

    if is_cold:
        logger.info(
            "[HYBRID_SEARCH][WEIGHT] Cold Start 감지 → 전역 100%% 편향 적용 "
            "(masked_uid=%s, personalized=%.1f, global=%.1f)",
            masked_uid,
            _COLD_START_PERSONALIZED_WEIGHT,
            _COLD_START_GLOBAL_WEIGHT,
        )
        return _COLD_START_PERSONALIZED_WEIGHT, _COLD_START_GLOBAL_WEIGHT

    logger.debug(
        "[HYBRID_SEARCH][WEIGHT] 정상 사용자 가중치 적용 "
        "(masked_uid=%s, personalized=%.4f, global=%.4f)",
        masked_uid,
        _PERSONALIZED_INDEX_WEIGHT,
        _GLOBAL_INDEX_WEIGHT,
    )
    return _PERSONALIZED_INDEX_WEIGHT, _GLOBAL_INDEX_WEIGHT


async def _log_search_history_bg(hashed_user_id: str, query: str) -> None:
    """
    검색 히스토리 로깅 백그라운드 태스크 (Fire-and-Forget 전용).

    asyncio.create_task와 함께 사용하며, 검색 흐름과 분리된 코루틴에서
    Redis 로깅을 best-effort로 수행한다.
    실패 시에도 검색 응답에는 영향을 주지 않는다.

    [리뷰반영] search() 내부 클로저 대신 모듈 레벨 함수로 분리:
    - 매 호출마다 클로저 객체 재생성 없음 → 퍼-요청 오버헤드 최소화.
    - 독립적으로 테스트 가능한 순수 함수.
    """
    try:
        # [리뷰반영] 백그라운드 태스크 무한 대기 방지:
        # Redis 연결 지연이나 블로킹으로 인해 백그라운드 태스크가 쌓이는 것을 막기 위해 환경 변수로 설정 가능한 타임아웃 적용
        await asyncio.wait_for(
            topic_clustering_service.log_search_query(hashed_user_id, query),
            timeout=_LOG_SEARCH_HISTORY_TIMEOUT,
        )
    except asyncio.TimeoutError:
        # [리뷰반영] TimeoutError 분리:
        # 일시적인 지연(latency) 문제와 기능적 오류를 분리하여 장애 원인 분석의 정확도 향상
        logger.warning(
            "[HYBRID_SEARCH] 검색 히스토리 로깅 시간 초과 (timeout=%.1fs, hashed_user_id=%s).",
            _LOG_SEARCH_HISTORY_TIMEOUT,
            hashed_user_id,
        )
    except Exception:  # noqa: BLE001
        # 히스토리 로깅 실패는 검색 응답에 영향을 주지 않는다 (best-effort).
        # 쿼리 원문은 PII 노출 위험이 있으므로 로그에 포함하지 않는다.
        # [리뷰반영] PII 정책: 비-PII 식별자인 hashed_user_id를 로그에 포함하여 장애 연관성 추적 강화
        logger.warning(
            "[HYBRID_SEARCH] 검색 히스토리 로깅 실패 (기능적 오류, 검색 응답에는 영향 없음, hashed_user_id=%s).",
            hashed_user_id,
            exc_info=True,
        )

# [Optimization] 질의 분석용 정규식 패턴 (미리 컴파일하여 부하가 큰 런타임 성능 확보)
_SEMANTIC_PATTERN = re.compile(
    r"(어떻게|방법|이유|왜|설명|알려|정리|해줘|뭐야|란|무엇|인가요|나요|있나요|의미|뜻|차이|비교|특징)"
)
_KEYWORD_PATTERN = re.compile(
    r"([\"']).*?\1|"  # 따옴표로 감싸진 용어
    r"\d{4}[-./]\d{2}|"  # 날짜형 (YYYY-MM)
    r"v\d+\.\d+|"  # 버전형 (v1.0)
    r"(\w+-\d+)"  # 코드형 (예: ISS-614)
)


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
        user_info: Optional[Dict[str, Any]] = None,
    ) -> HybridSearchResult:
        """
        하이브리드 검색 수행 (캐싱 및 로깅 포함).
        - 사용자 히스토리를 기록 (비로그인/Mock 포함).
        - Redis 캐시를 먼저 확인하고, 미스 시 실제 검색 수행.
        - 실제 검색은 CPU-bound 이므로 threadpool에서 실행.

        [Fail Fast 정책] 파라미터 검증은 이 public 진입점에서만 수행합니다.
        """
        # [Fail Fast] 캐시 접근 전 파라미터 유효 범위 검증 (단일 검증 지점)
        if not (0.0 <= alpha <= 1.0):
            raise ValueError(f"alpha must be between 0.0 and 1.0, got {alpha}")
        if k < 1:
            raise ValueError(f"k must be greater than or equal to 1, got {k}")

        # 0. 히스토리 로깅 (Best-effort, Fire-and-Forget)
        # PII 정책: user_id는 반드시 해싱(mask_pii_id)하여 전달한다.
        # [리뷰반영] 모듈 레벨 _log_search_history_bg로 분리:
        #   - 클로저 재생성 없음 → 퍼 요청 오버헤드 최소화.
        #   - 실패 인식/예외 체인이 함수 내부에서 완결되어 테스트 용이.
        if user_info and "id" in user_info:
            user_id_raw = str(user_info["id"])
            hashed_user_id = mask_pii_id(user_id_raw, truncate_len=0)  # 전체 해시 확보
            asyncio.create_task(_log_search_history_bg(hashed_user_id, query))

        # 1. PARA 카테고리 검증 및 필터 병합
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

        # A. Semantic Bias (Dense 우선): 질문형, 설명 요청, 자연어 문장 패턴
        if _SEMANTIC_PATTERN.search(query):
            return 0.7

        # B. Keyword Bias (Sparse 우선): 고유 명사, 코드, 날짜, 인용구 패턴
        if _KEYWORD_PATTERN.search(query):
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

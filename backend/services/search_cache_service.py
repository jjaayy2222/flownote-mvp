# backend/services/search_cache_service.py

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
from backend.services.redis_pubsub import redis_client

logger = logging.getLogger(__name__)

# alpha를 반올림할 소수점 자리수.
# IEEE 754 부동소수점 표현 오류로 인한 캐시 미스를 방지합니다.
# (예: 0.1 + 0.2 == 0.30000000000000004)
_ALPHA_ROUND_NDIGITS = 6


class SearchCacheService:
    """
    하이브리드 검색 결과를 위한 Redis 캐싱 서비스.
    - 반복되는 동일 쿼리 및 필터 조합에 대해 빠른 응답 보장.
    - Redis 연결 실패 시 자동으로 로컬 검색으로 폴백 (Pass-through).
    """

    def __init__(self, ttl: int = 3600):
        self.ttl = ttl  # 기본 캐시 유지 시간: 1시간

    def _generate_key(
        self,
        query: str,
        k: int,
        alpha: float,
        metadata_filter: Optional[Dict],
        filter_expansion_factor: int,
    ) -> str:
        """검색 파라미터를 기반으로 고유한 캐시 키 생성.

        [Review 반영]
        - alpha: IEEE 754 부동소수점 오류로 인한 캐시 미스 방지를 위해 정규화.
        - filter_expansion_factor: 검색 결과에 영향을 미치므로 반드시 키에 포함.
        """
        # [Review 반영] alpha 정규화: 부동소수점 표현 불일치로 인한 캐시 미스 방지
        normalized_alpha = round(alpha, _ALPHA_ROUND_NDIGITS)
        # 필터 딕셔너리를 정렬된 JSON 문자열로 변환하여 일관성 유지
        filter_str = (
            json.dumps(metadata_filter, sort_keys=True) if metadata_filter else "{}"
        )
        # [Review 반영] filter_expansion_factor 포함: 다른 expansion 값은 다른 결과를 생성
        params_str = (
            f"{query}:{k}:{normalized_alpha}:{filter_str}:{filter_expansion_factor}"
        )
        params_hash = hashlib.sha256(params_str.encode()).hexdigest()
        return f"hybrid_search:{params_hash}"

    async def get_results(
        self,
        query: str,
        k: int,
        alpha: float,
        metadata_filter: Optional[Dict],
        filter_expansion_factor: int,
    ) -> Optional[List[Dict]]:
        """캐시에서 결과 조회"""
        if not redis_client.is_connected():
            return None

        key = self._generate_key(
            query, k, alpha, metadata_filter, filter_expansion_factor
        )
        try:
            cached_data = await redis_client.redis.get(key)
            if cached_data is not None:
                # 빈 결과([])도 유효한 캐시 히트로 취급
                logger.info("Search cache hit: query_len=%d", len(query))
                return json.loads(cached_data)
        except Exception as e:
            logger.warning("Failed to retrieve search results from cache: %s", e)

        return None

    async def set_results(
        self,
        query: str,
        k: int,
        alpha: float,
        metadata_filter: Optional[Dict],
        filter_expansion_factor: int,
        results: List[Dict],
    ) -> None:
        """검색 결과를 캐시에 저장"""
        if not redis_client.is_connected():
            return

        key = self._generate_key(
            query, k, alpha, metadata_filter, filter_expansion_factor
        )
        try:
            # JSON 직렬화 안전성 확보
            # 리스트 내부의 점수(score) 등 혹시 모를 numpy 타입을 Python 기본 타입으로 변환
            serialized = json.dumps(results, default=self._json_default)
            await redis_client.redis.set(key, serialized, ex=self.ttl)
            logger.debug("Search results cached: query_len=%d", len(query))
        except Exception as e:
            logger.warning("Failed to cache search results: %s", e)

    @staticmethod
    def _json_default(obj: Any) -> Any:
        """JSON 직렬화 불가능한 타입(예: numpy float)을 위한 헬퍼"""
        import numpy as np

        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# 싱글톤 인스턴스
search_cache_service = SearchCacheService()

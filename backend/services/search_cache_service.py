# backend/services/search_cache_service.py

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
from backend.services.redis_pubsub import redis_client

logger = logging.getLogger(__name__)


class SearchCacheService:
    """
    하이브리드 검색 결과를 위한 Redis 캐싱 서비스.
    - 반복되는 동일 쿼리 및 필터 조합에 대해 빠른 응답 보장.
    - Redis 연결 실패 시 자동으로 로컬 검색으로 폴백 (Pass-through).
    """

    def __init__(self, ttl: int = 3600):
        self.ttl = ttl  # 기본 캐시 유지 시간: 1시간

    def _generate_key(
        self, query: str, k: int, alpha: float, metadata_filter: Optional[Dict]
    ) -> str:
        """검색 파라미터를 기반으로 고유한 캐시 키 생성"""
        # 필터 딕셔너리를 정렬된 JSON 문자열로 변환하여 일관성 유지
        filter_str = (
            json.dumps(metadata_filter, sort_keys=True) if metadata_filter else "{}"
        )
        params_str = f"{query}:{k}:{alpha}:{filter_str}"
        params_hash = hashlib.sha256(params_str.encode()).hexdigest()
        return f"hybrid_search:{params_hash}"

    async def get_results(
        self, query: str, k: int, alpha: float, metadata_filter: Optional[Dict]
    ) -> Optional[List[Dict]]:
        """캐시에서 결과 조회"""
        if not redis_client.is_connected():
            return None

        key = self._generate_key(query, k, alpha, metadata_filter)
        try:
            cached_data = await redis_client.redis.get(key)
            if cached_data is not None:
                # [Review 반영] 빈 결과([])도 유효한 캐시 히트로 취급
                logger.info("Search cache hit: query=%s", query)
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
        results: List[Dict],
    ):
        """검색 결과를 캐시에 저장"""
        if not redis_client.is_connected():
            return

        key = self._generate_key(query, k, alpha, metadata_filter)
        try:
            # [Review 반영] JSON 직렬화 안전성 확보
            # 리스트 내부의 점수(score) 등 혹시 모를 numpy 타입을 Python 기본 타입으로 변환
            serialized = json.dumps(results, default=self._json_default)
            await redis_client.redis.set(key, serialized, ex=self.ttl)
            logger.debug("Search results cached: query=%s", query)
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

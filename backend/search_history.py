# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/search_history.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - 검색 히스토리 관리
[EN] FlowNote MVP - Search History Management
"""

import json
import os
import uuid
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional, TypedDict


class SearchStatistics(TypedDict):
    """
    [KO] 검색 통계 반환 타입
    [EN] Return type for search statistics
    """

    total_searches: int
    avg_results: float
    most_common_query: Optional[str]


class SearchHistory:
    """
    [KO] 검색 히스토리를 로컬 JSON 파일에 영속화하고 관리하는 클래스.
    [EN] A class to persist and manage search history in a local JSON file.
    """

    def __init__(self, storage_path: str = "data/search_history.json"):
        """
        [KO] 히스토리 저장 경로를 설정하고 기존 데이터를 로드합니다.
        [EN] Sets the history storage path and loads existing data.

        Args:
            storage_path (str): [KO] 히스토리를 저장할 JSON 파일 경로 / [EN] JSON file path to store history
        """
        self.storage_path = storage_path
        self.history: Dict[str, Dict] = {}
        self._load_history()

    def _load_history(self):
        """
        [KO] 지정된 경로에서 저장된 검색 히스토리를 로드합니다. 파일이 없으면 새로 생성합니다.
        [EN] Loads saved search history from the specified path. Creates it if it doesn't exist.
        """
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception as e:
                print(f"히스토리 로드 실패: {e}")
                self.history = {}
        else:
            # data 폴더 확인
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            self.history = {}

    def _save_history(self):
        """
        [KO] 메모리의 히스토리 데이터를 JSON 파일에 저장합니다.
        [EN] Saves the in-memory history data to a JSON file.
        """
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"히스토리 저장 실패: {e}")

    def add_search(
        self, query: str, results_count: int, top_results: Optional[List[str]] = None
    ) -> str:
        """
        [KO] 새로운 검색 기록을 추가하고 저장합니다.
        [EN] Adds and saves a new search record.

        Args:
            query (str): [KO] 검색에 사용된 쿼리 문자열 / [EN] Query string used for the search
            results_count (int): [KO] 검색된 결과의 총 개수 / [EN] Total number of retrieved results
            top_results (List[str], optional): [KO] 상위 검색 결과 미리보기 텍스트 리스트 / [EN] List of preview texts for top search results

        Returns:
            str: [KO] 새로 생성된 검색 고유 ID / [EN] Newly generated unique search ID
        """
        # 검색 ID 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        search_id = f"search_{timestamp}_{unique_id}"

        # 히스토리 생성
        self.history[search_id] = {
            "query": query,
            "results_count": results_count,
            "top_results": top_results[:3] if top_results else [],
            "search_time": datetime.now().isoformat(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 저장
        self._save_history()

        return search_id

    def get_search(self, search_id: str) -> Optional[Dict]:
        """
        [KO] 특정 검색 ID에 해당하는 기록을 조회합니다.
        [EN] Retrieves the record corresponding to a specific search ID.

        Args:
            search_id (str): [KO] 조회할 검색 고유 ID / [EN] Unique search ID to retrieve

        Returns:
            Optional[Dict]: [KO] 검색 히스토리 딕셔너리 (존재하지 않으면 None) / [EN] Search history dictionary (None if not found)
        """
        return self.history.get(search_id)

    def get_recent_searches(self, limit: int = 10) -> List[Dict]:
        """
        [KO] 최근 수행된 검색 기록들을 최신순으로 정렬하여 조회합니다.
        [EN] Retrieves recently performed search records, sorted from newest to oldest.

        Args:
            limit (int): [KO] 반환할 최대 결과 수 / [EN] Maximum number of results to return

        Returns:
            List[Dict]: [KO] 최신순으로 정렬된 검색 기록 리스트 / [EN] List of search records sorted by newest first
        """
        # 시간순 정렬 (최신순)
        sorted_history = sorted(
            self.history.items(), key=lambda x: x[1]["search_time"], reverse=True
        )

        # 상위 limit개 반환
        return [{"id": sid, **info} for sid, info in sorted_history[:limit]]

    def get_all_searches(self) -> Dict[str, Dict]:
        """
        [KO] 저장된 모든 검색 기록을 조회합니다.
        [EN] Retrieves all saved search records.

        Returns:
            Dict[str, Dict]: [KO] 전체 검색 히스토리를 담은 딕셔너리 / [EN] Dictionary containing the entire search history
        """
        return self.history

    def delete_search(self, search_id: str) -> bool:
        """
        [KO] 특정 검색 ID의 기록을 삭제합니다.
        [EN] Deletes the record for a specific search ID.

        Args:
            search_id (str): [KO] 삭제할 검색 고유 ID / [EN] Unique search ID to delete

        Returns:
            bool: [KO] 삭제 성공 시 True, 실패 시(ID 없음) False / [EN] True if successfully deleted, False otherwise (ID not found)
        """
        if search_id in self.history:
            del self.history[search_id]
            self._save_history()
            return True
        return False

    def clear_all(self):
        """
        [KO] 모든 검색 기록을 영구적으로 삭제합니다.
        [EN] Permanently clears all search records.
        """
        self.history = {}
        self._save_history()

    def get_statistics(self) -> SearchStatistics:
        """
        [KO] 누적된 검색 히스토리를 바탕으로 통계 정보를 계산합니다.
        [EN] Calculates statistical information based on the accumulated search history.

        [KO] 성능 최적화: 가장 많이 검색된 쿼리를 찾을 때 O(n) 복잡도를 가지는 `collections.Counter`를 사용합니다.
        [EN] Performance optimization: Uses `collections.Counter` with O(n) complexity to find the most common query.

        Returns:
            SearchStatistics: [KO] 총 검색 횟수, 평균 결과 수, 최다 검색 쿼리를 포함하는 통계 딕셔너리
                              / [EN] Statistics dictionary containing total searches, average results count, and most common query
        """
        if not self.history:
            return {"total_searches": 0, "avg_results": 0.0, "most_common_query": None}

        # 전체 검색 수
        total_searches = len(self.history)

        # 평균 결과 수
        avg_results = (
            sum(h["results_count"] for h in self.history.values()) / total_searches
        )

        # 가장 많이 검색된 쿼리 (메모리 최적화: 제너레이터 사용)
        query_counts = Counter(h["query"] for h in self.history.values())
        top_queries = query_counts.most_common(1)
        most_common = top_queries[0][0] if top_queries else None

        return {
            "total_searches": total_searches,
            "avg_results": round(avg_results, 1),
            "most_common_query": most_common,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테스트 코드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    print("=" * 50)
    print("검색 히스토리 테스트")
    print("=" * 50)

    # 히스토리 관리자 생성
    history = SearchHistory()

    # 테스트 검색 추가
    print("\n1. 검색 기록 추가 테스트")
    print("-" * 50)

    search_id1 = history.add_search(
        query="FlowNote 사용법",
        results_count=5,
        top_results=[
            "FlowNote는 AI 대화 관리 도구입니다.",
            "파일 업로드 기능을 제공합니다.",
            "검색 기능이 강력합니다.",
        ],
    )
    print(f"✅ 검색 추가 완료: {search_id1}")

    search_id2 = history.add_search(
        query="임베딩이란",
        results_count=8,
        top_results=[
            "임베딩은 텍스트를 벡터로 변환합니다.",
            "유사도 검색에 사용됩니다.",
        ],
    )
    print(f"✅ 검색 추가 완료: {search_id2}")

    search_id3 = history.add_search(
        query="FlowNote 사용법",  # 중복 검색
        results_count=5,
        top_results=["FlowNote는 간단합니다."],
    )
    print(f"✅ 검색 추가 완료: {search_id3}")

    # 최근 검색 조회
    print("\n2. 최근 검색 조회 테스트")
    print("-" * 50)

    recent = history.get_recent_searches(limit=5)
    print(f"📚 최근 검색 {len(recent)}개:")
    for i, search in enumerate(recent, 1):
        print(f"\n{i}. {search['query']}")
        print(f"   - 결과: {search['results_count']}개")
        print(f"   - 시간: {search['created_at']}")

    # 통계
    print("\n3. 통계 테스트")
    print("-" * 50)

    stats = history.get_statistics()
    print("📊 통계:")
    print(f"   - 총 검색: {stats['total_searches']}회")
    print(f"   - 평균 결과: {stats['avg_results']}개")
    print(f"   - 자주 검색: {stats['most_common_query']}")

    print("\n" + "=" * 50)
    print("테스트 완료!")
    print("=" * 50)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/search_history.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - 검색 히스토리 관리
[EN] FlowNote MVP - Search History Management
"""

import json
import logging
import os
import uuid
from collections import Counter
from datetime import date, datetime
from typing import Any, Dict, List, Optional, TypedDict

from backend.utils.common import format_error_msg

logger = logging.getLogger(__name__)


def _custom_json_serializer(obj: Any) -> str:
    """JSON 직렬화 불가 객체를 위한 커스텀 직렬화 헬퍼"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


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
        [KO]
        히스토리 저장 경로를 설정하고 기존 데이터를 로드합니다.

        Args:
            storage_path: 히스토리를 저장할 JSON 파일 경로

        [EN]
        Sets the history storage path and loads existing data.

        Args:
            storage_path: JSON file path to store history
        """
        self.storage_path = storage_path
        self.history: Dict[str, Dict] = {}
        self._load_history()

    def _load_history(self):
        """
        [KO]
        지정된 경로에서 저장된 검색 히스토리를 로드합니다. 파일이 없으면 새로 생성합니다.

        [EN]
        Loads saved search history from the specified path. Creates it if it doesn't exist.
        """
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except (OSError, ValueError, json.JSONDecodeError) as e:
                logger.warning(
                    f"히스토리 로드 실패: {type(e).__name__}: {format_error_msg(e)}",
                    extra={
                        "action": "load_history",
                        "path": self.storage_path,
                        "error_type": type(e).__name__,
                    },
                )
                self.history = {}
        else:
            # data 폴더 확인
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            self.history = {}

    def _save_history(self) -> bool:
        """
        [KO]
        메모리의 히스토리 데이터를 JSON 파일에 저장합니다.

        Returns:
            저장 성공 시 True, 직렬화 또는 I/O 실패 시 False

        [EN]
        Saves the in-memory history data to a JSON file.

        Returns:
            True if saved successfully, False on serialization or I/O failure.
        """
        # [KO] 1단계: 직렬화 - 파일 I/O와 분리하여 예외 범위를 명확히 제한
        # [EN] Step 1: Serialization — separated from file I/O to narrow the exception scope
        try:
            serialized = json.dumps(
                self.history,
                ensure_ascii=False,
                indent=2,
                default=_custom_json_serializer,
            )
        except (TypeError, ValueError) as e:
            logger.error(
                f"히스토리 직렬화 실패: {type(e).__name__}: {format_error_msg(e)}",
                extra={
                    "action": "save_history_serialize",
                    "path": self.storage_path,
                    "error_type": type(e).__name__,
                },
            )
            return False

        # [KO] 2단계: 파일 I/O - 직렬화 성공 후에만 파일에 기록
        # [EN] Step 2: File I/O — only writes to disk after successful serialization
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                f.write(serialized)
        except OSError as e:
            logger.error(
                f"히스토리 저장 실패: {type(e).__name__}: {format_error_msg(e)}",
                extra={
                    "action": "save_history_write",
                    "path": self.storage_path,
                    "error_type": type(e).__name__,
                },
            )
            return False

        return True

    def add_search(
        self, query: str, results_count: int, top_results: Optional[List[str]] = None
    ) -> str:
        """
        [KO]
        새로운 검색 기록을 추가하고 저장합니다.

        Args:
            query: 검색에 사용된 쿼리 문자열
            results_count: 검색된 결과의 총 개수
            top_results: 상위 검색 결과 미리보기 텍스트 리스트

        Returns:
            새로 생성된 검색 고유 ID

        [EN]
        Adds and saves a new search record.

        Args:
            query: Query string used for the search
            results_count: Total number of retrieved results
            top_results: List of preview texts for top search results

        Returns:
            Newly generated unique search ID
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

        # [KO] 저장 - 실패 시 메모리에서도 롤백하여 일관성 유지
        # [EN] Save — roll back from memory on failure to maintain consistency
        if not self._save_history():
            del self.history[search_id]
            logger.error(
                "히스토리 저장 실패로 검색 기록 추가가 취소되었습니다.",
                extra={"action": "add_search_rollback", "error_type": "save_failure"},
            )

        return search_id

    def get_search(self, search_id: str) -> Optional[Dict]:
        """
        [KO]
        특정 검색 ID에 해당하는 기록을 조회합니다.

        Args:
            search_id: 조회할 검색 고유 ID

        Returns:
            해당 ID의 검색 기록 딕셔너리(키: query, results_count, top_results, search_time, created_at), 없으면 None

        [EN]
        Retrieves the record corresponding to a specific search ID.

        Args:
            search_id: Unique search ID to retrieve

        Returns:
            Search record dict (keys: query, results_count, top_results, search_time, created_at), or None if not found
        """
        return self.history.get(search_id)

    def get_recent_searches(self, limit: int = 10) -> List[Dict]:
        """
        [KO]
        최근 수행된 검색 기록들을 최신순으로 정렬하여 조회합니다.

        Args:
            limit: 반환할 최대 결과 수

        Returns:
            최신순 정렬된 검색 기록 리스트. 각 항목은 id, query, results_count, top_results, search_time, created_at 키를 포함

        [EN]
        Retrieves recently performed search records, sorted from newest to oldest.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of search records sorted newest-first; each item contains id, query, results_count, top_results, search_time, created_at
        """
        # 시간순 정렬 (최신순)
        sorted_history = sorted(
            self.history.items(), key=lambda x: x[1]["search_time"], reverse=True
        )

        # 상위 limit개 반환
        return [{"id": sid, **info} for sid, info in sorted_history[:limit]]

    def get_all_searches(self) -> Dict[str, Dict]:
        """
        [KO]
        저장된 모든 검색 기록을 조회합니다.

        Returns:
            search_id를 키, 검색 기록 딕셔너리를 값으로 하는 전체 히스토리

        [EN]
        Retrieves all saved search records.

        Returns:
            Full history dict keyed by search_id, with each value being a search record dict
        """
        return self.history

    def delete_search(self, search_id: str) -> bool:
        """
        [KO]
        특정 검색 ID의 기록을 삭제합니다.

        Args:
            search_id: 삭제할 검색 고유 ID

        Returns:
            삭제 성공 시 True, 실패 시(ID 없음) False

        [EN]
        Deletes the record for a specific search ID.

        Args:
            search_id: Unique search ID to delete

        Returns:
            True if successfully deleted, False otherwise (ID not found)
        """
        if search_id in self.history:
            record = self.history.pop(search_id)
            # [KO] 저장 실패 시 삭제된 레코드를 메모리에 복원하여 일관성 유지
            # [EN] Restore the deleted record on save failure to maintain consistency
            if not self._save_history():
                self.history[search_id] = record
                logger.error(
                    "히스토리 저장 실패로 검색 기록 삭제가 취소되었습니다.",
                    extra={
                        "action": "delete_search_rollback",
                        "error_type": "save_failure",
                    },
                )
                return False
            return True
        return False

    def clear_all(self):
        """
        [KO]
        모든 검색 기록을 영구적으로 삭제합니다.

        [EN]
        Permanently clears all search records.
        """
        prev_history = self.history
        self.history = {}
        # [KO] 저장 실패 시 이전 히스토리를 메모리에 복원하여 일관성 유지
        # [EN] Restore previous history on save failure to maintain consistency
        if not self._save_history():
            self.history = prev_history
            logger.error(
                "히스토리 저장 실패로 전체 삭제가 취소되었습니다.",
                extra={"action": "clear_all_rollback", "error_type": "save_failure"},
            )

    def get_statistics(self) -> SearchStatistics:
        """
        [KO]
        누적된 검색 히스토리를 바탕으로 통계 정보를 계산합니다.
        성능 최적화: 가장 많이 검색된 쿼리를 찾을 때 O(n) 복잡도를 가지는 `collections.Counter`를 사용합니다.

        Returns:
            총 검색 횟수, 평균 결과 수, 최다 검색 쿼리를 포함하는 통계 딕셔너리

        [EN]
        Calculates statistical information based on the accumulated search history.
        Performance optimization: Uses `collections.Counter` with O(n) complexity to find the most common query.

        Returns:
            Statistics dictionary containing total searches, average results count, and most common query
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

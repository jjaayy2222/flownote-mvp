# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/search_history.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 검색 히스토리 관리
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional


class SearchHistory:
    """검색 히스토리 관리 클래스"""

    def __init__(self, storage_path: str = "data/search_history.json"):
        """
        Args:
            storage_path: 히스토리 저장 경로
        """
        self.storage_path = storage_path
        self.history: Dict[str, Dict] = {}
        self._load_history()

    def _load_history(self):
        """저장된 히스토리 로드"""
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
        """히스토리 저장"""
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"히스토리 저장 실패: {e}")

    def add_search(
        self, query: str, results_count: int, top_results: List[str] = None
    ) -> str:
        """
        검색 기록 추가

        Args:
            query: 검색 쿼리
            results_count: 결과 개수
            top_results: 상위 결과 미리보기 (선택)

        Returns:
            search_id: 생성된 검색 ID
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
        검색 기록 조회

        Args:
            search_id: 검색 ID

        Returns:
            히스토리 딕셔너리 또는 None
        """
        return self.history.get(search_id)

    def get_recent_searches(self, limit: int = 10) -> List[Dict]:
        """
        최근 검색 기록 조회

        Args:
            limit: 조회할 개수

        Returns:
            최근 검색 기록 리스트
        """
        # 시간순 정렬 (최신순)
        sorted_history = sorted(
            self.history.items(), key=lambda x: x[1]["search_time"], reverse=True
        )

        # 상위 limit개 반환
        return [{"id": sid, **info} for sid, info in sorted_history[:limit]]

    def get_all_searches(self) -> Dict[str, Dict]:
        """
        모든 검색 기록 조회

        Returns:
            전체 히스토리 딕셔너리
        """
        return self.history

    def delete_search(self, search_id: str) -> bool:
        """
        검색 기록 삭제

        Args:
            search_id: 검색 ID

        Returns:
            삭제 성공 여부
        """
        if search_id in self.history:
            del self.history[search_id]
            self._save_history()
            return True
        return False

    def clear_all(self):
        """모든 검색 기록 삭제"""
        self.history = {}
        self._save_history()

    def get_statistics(self) -> Dict:
        """
        검색 통계 계산

        Returns:
            통계 딕셔너리
        """
        if not self.history:
            return {"total_searches": 0, "avg_results": 0, "most_common_query": None}

        # 전체 검색 수
        total_searches = len(self.history)

        # 평균 결과 수
        avg_results = (
            sum(h["results_count"] for h in self.history.values()) / total_searches
        )

        # 가장 많이 검색된 쿼리
        queries = [h["query"] for h in self.history.values()]
        if queries:
            most_common = max(set(queries), key=queries.count)
        else:
            most_common = None

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
    print(f"📊 통계:")
    print(f"   - 총 검색: {stats['total_searches']}회")
    print(f"   - 평균 결과: {stats['avg_results']}개")
    print(f"   - 자주 검색: {stats['most_common_query']}")

    print("\n" + "=" * 50)
    print("테스트 완료!")
    print("=" * 50)


"""result

    ==================================================
    검색 히스토리 테스트
    ==================================================

    1. 검색 기록 추가 테스트
    --------------------------------------------------
    ✅ 검색 추가 완료: search_20251025_133526_a51705db
    ✅ 검색 추가 완료: search_20251025_133526_153790eb
    ✅ 검색 추가 완료: search_20251025_133526_2df8ccf9

    2. 최근 검색 조회 테스트
    --------------------------------------------------
    📚 최근 검색 3개:

    1. FlowNote 사용법
        - 결과: 5개
        - 시간: 2025-10-25 13:35:26

    2. 임베딩이란
        - 결과: 8개
        - 시간: 2025-10-25 13:35:26

    3. FlowNote 사용법
        - 결과: 5개
        - 시간: 2025-10-25 13:35:26

    3. 통계 테스트
    --------------------------------------------------
    📊 통계:
        - 총 검색: 3회
        - 평균 결과: 6.0개
        - 자주 검색: FlowNote 사용법

    ==================================================
    테스트 완료!
    ==================================================

"""


"""result_2

    ==================================================
    검색 히스토리 테스트
    ==================================================

    1. 검색 기록 추가 테스트
    --------------------------------------------------
    ✅ 검색 추가 완료: search_20251025_145632_376fe2ab
    ✅ 검색 추가 완료: search_20251025_145632_c394435e
    ✅ 검색 추가 완료: search_20251025_145632_d20d291c

    2. 최근 검색 조회 테스트
    --------------------------------------------------
    📚 최근 검색 5개:

    1. FlowNote 사용법
        - 결과: 5개
        - 시간: 2025-10-25 14:56:32

    2. 임베딩이란
        - 결과: 8개
        - 시간: 2025-10-25 14:56:32

    3. FlowNote 사용법
        - 결과: 5개
        - 시간: 2025-10-25 14:56:32

    4. FlowNote 사용법
        - 결과: 5개
        - 시간: 2025-10-25 13:35:26

    5. 임베딩이란
        - 결과: 8개
        - 시간: 2025-10-25 13:35:26

    3. 통계 테스트
    --------------------------------------------------
    📊 통계:
        - 총 검색: 6회
        - 평균 결과: 6.0개
        - 자주 검색: FlowNote 사용법

    ==================================================
    테스트 완료!
    ==================================================

"""


"""result_3

    ==================================================
    검색 히스토리 테스트
    ==================================================

    1. 검색 기록 추가 테스트
    --------------------------------------------------
    ✅ 검색 추가 완료: search_20251025_151552_3c85657e
    ✅ 검색 추가 완료: search_20251025_151552_bd489c20
    ✅ 검색 추가 완료: search_20251025_151552_c5bbe03f

    2. 최근 검색 조회 테스트
    --------------------------------------------------
    📚 최근 검색 5개:

    1. FlowNote 사용법
        - 결과: 5개
        - 시간: 2025-10-25 15:15:52

    2. 임베딩이란
        - 결과: 8개
        - 시간: 2025-10-25 15:15:52

    3. FlowNote 사용법
        - 결과: 5개
        - 시간: 2025-10-25 15:15:52

    4. 임베딩
        - 결과: 0개
        - 시간: 2025-10-25 15:09:10

    5. 쿼리
        - 결과: 0개
        - 시간: 2025-10-25 15:08:59

    3. 통계 테스트
    --------------------------------------------------
    📊 통계:
        - 총 검색: 13회
        - 평균 결과: 4.2개
        - 자주 검색: FlowNote 사용법

    ==================================================
    테스트 완료!
    ==================================================

"""

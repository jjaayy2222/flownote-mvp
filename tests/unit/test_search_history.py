# tests/unit/test_search_history.py

"""
[KO] backend/search_history.py SearchHistory에 대한 단위 테스트.
[EN] Unit tests for SearchHistory in backend/search_history.py.

테스트 범위:
- 파일 I/O 실패 시 격리 (mocking) + 원자적 쓰기 검증
- 손상된 데이터(JSON 파싱 오류, dict 미준수) 복원력 + 경고 로그 발생 검증
- 검색 기록 최대 보관 수(limit) 슬라이싱 + 최신 항목 선택 검증
- add_search / get_search / get_recent_searches / get_all_searches 내용 검증
- delete_search / clear_all 삭제 및 정확한 롤백 스냅샷 검증
- _apply_and_persist 롤백 패턴 (정확한 히스토리 동등성)
- get_statistics 반올림 회귀 감지
- 4차 리뷰 전방위 대응 검증 (심볼릭 링크 탈출 차단, 파일 락 타임아웃 및 fail-closed,
  0o600 권한 강제, fsync 호출, per-user 프루닝, 디스크 즉시 동기화, 사용자 격리)
"""

import json
import logging
import os
import stat
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

from backend.search_history import SearchHistory, _custom_json_serializer

# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────


@pytest.fixture
def tmp_history_file(tmp_path: Path) -> Generator[str, None, None]:
    """격리된 임시 JSON 파일 경로를 반환합니다."""
    storage = tmp_path / "data" / "search_history.json"
    yield str(storage)


@pytest.fixture
def sh(tmp_history_file: str) -> SearchHistory:
    """빈 SearchHistory 인스턴스를 반환합니다."""
    return SearchHistory(storage_path=tmp_history_file)


# ─────────────────────────────────────────────────────────
# 초기화 및 로드 테스트
# ─────────────────────────────────────────────────────────


class TestSearchHistoryInit:
    """초기화 및 _load_history 로직을 검증합니다."""

    def test_init_creates_empty_history_when_file_absent(self, tmp_history_file: str):
        """파일이 없을 때 빈 히스토리로 초기화됩니다."""
        sh = SearchHistory(storage_path=tmp_history_file)
        assert not sh.history

    def test_init_creates_data_directory_when_absent(self, tmp_path: Path):
        """부모 디렉터리가 없어도 자동 생성됩니다."""
        storage = str(tmp_path / "nested" / "dir" / "history.json")
        sh = SearchHistory(storage_path=storage)
        assert not sh.history
        assert os.path.isdir(str(tmp_path / "nested" / "dir"))

    def test_init_rejects_non_positive_max_history_entries(self, tmp_history_file: str):
        """Comment 8 & 12: 0 또는 음수 max_history_entries 설정 시 ValueError가 발생합니다."""
        with pytest.raises(ValueError, match="positive integer"):
            SearchHistory(storage_path=tmp_history_file, max_history_entries=0)

        with pytest.raises(ValueError, match="positive integer"):
            SearchHistory(storage_path=tmp_history_file, max_history_entries=-5)

    def test_init_rejects_non_int_max_history_entries(self, tmp_history_file: str):
        """Comment 7: float 또는 bool 등 non-int 전달 시 TypeError가 발생합니다."""
        with pytest.raises(TypeError, match="plain int"):
            SearchHistory(storage_path=tmp_history_file, max_history_entries=2.5)  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="plain int"):
            SearchHistory(storage_path=tmp_history_file, max_history_entries=True)  # type: ignore[arg-type]

    def test_init_logs_warning_when_user_id_is_none(
        self, tmp_history_file: str, caplog: pytest.LogCaptureFixture
    ):
        """Comment 2: user_id=None 으로 초기화 시 공유 파일 보안 경고 로그가 기록됩니다."""
        with caplog.at_level(logging.WARNING, logger="backend.search_history"):
            SearchHistory(storage_path=tmp_history_file, user_id=None)

        assert any(
            "SearchHistory initialized without user_id" in record.message
            for record in caplog.records
        )

    def test_load_history_reads_existing_valid_json(self, tmp_history_file: str):
        """유효한 JSON이 있으면 그대로 로드됩니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        seed = {
            "search_20260101_120000_abcdef01": {
                "query": "hello",
                "results_count": 3,
                "top_results": [],
                "search_time": "2026-01-01T12:00:00",
                "created_at": "2026-01-01 12:00:00",
            }
        }
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            json.dump(seed, f)

        sh = SearchHistory(storage_path=tmp_history_file)
        assert "search_20260101_120000_abcdef01" in sh.history
        assert sh.history["search_20260101_120000_abcdef01"]["query"] == "hello"

    def test_load_history_prunes_records_exceeding_max_entries_and_persists(
        self, tmp_history_file: str
    ):
        """Comment 11 & 12: 로드 시 max_history_entries를 초과하는 기록이 있으면 즉시 프루닝하고 파일에도 저장합니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        seed = {
            f"search_{i}": {
                "query": f"q_{i}",
                "results_count": i,
                "top_results": [],
                "search_time": f"2026-01-01T12:00:{i:02d}",
                "created_at": "2026-01-01 12:00:00",
            }
            for i in range(10)
        }
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            json.dump(seed, f)

        sh = SearchHistory(storage_path=tmp_history_file, max_history_entries=4)
        assert len(sh.history) == 4

        # Comment 12: 디스크 파일에도 4개로 줄어든 상태가 반영되어 있어야 함
        with open(tmp_history_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        assert len(disk_data) == 4

    def test_load_history_falls_back_to_empty_on_corrupt_json(
        self, tmp_history_file: str, caplog: pytest.LogCaptureFixture
    ):
        """손상된 JSON 파일이 있을 때 빈 히스토리로 폴백되고 경고 로그가 발생합니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            f.write("{corrupt: json,,}")

        with caplog.at_level(logging.WARNING, logger="backend.search_history"):
            sh = SearchHistory(storage_path=tmp_history_file)

        assert not sh.history
        assert any("히스토리 로드 실패" in record.message for record in caplog.records)

    def test_load_history_falls_back_to_empty_on_non_dict_json(
        self, tmp_history_file: str, caplog: pytest.LogCaptureFixture
    ):
        """Comment 6: JSON 최상위가 dict가 아닌 배열/리스트인 경우 빈 히스토리로 폴백되고 경고가 기록됩니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            json.dump(["not", "a", "dict"], f)

        with caplog.at_level(logging.WARNING, logger="backend.search_history"):
            sh = SearchHistory(storage_path=tmp_history_file)

        assert sh.history == {}
        assert any("dict가 아닌 타입" in record.message for record in caplog.records)

    def test_load_history_falls_back_to_empty_on_oserror(self, tmp_history_file: str):
        """파일 읽기 중 OSError가 발생하면 빈 히스토리로 폴백됩니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            json.dump({}, f)

        sh = SearchHistory.__new__(SearchHistory)
        sh.storage_path = tmp_history_file
        sh._trusted_base_dir = os.path.dirname(os.path.abspath(tmp_history_file))
        sh.max_history_entries = 1000
        sh.user_id = None
        sh.history = {}
        with patch("builtins.open", side_effect=OSError("mock read failure")):
            sh._load_history()
        assert not sh.history


# ─────────────────────────────────────────────────────────
# add_search 테스트
# ─────────────────────────────────────────────────────────


class TestAddSearch:
    """add_search 메서드를 검증합니다."""

    def test_add_search_returns_string_id(self, sh: SearchHistory):
        """성공적인 추가는 search_ 접두어가 붙은 문자열 ID를 반환합니다."""
        sid = sh.add_search("테스트 쿼리", results_count=5)
        assert isinstance(sid, str)
        assert sid.startswith("search_")

    def test_add_search_stores_query_and_count(self, sh: SearchHistory):
        """추가된 레코드에 query와 results_count가 올바르게 저장됩니다."""
        sid = sh.add_search("검색어", results_count=7)
        assert sid is not None
        record = sh.history[sid]
        assert record["query"] == "검색어"
        assert record["results_count"] == 7

    def test_add_search_top_results_capped_at_three(self, sh: SearchHistory):
        """top_results는 최대 3개만 저장됩니다."""
        sid = sh.add_search("q", 10, top_results=["a", "b", "c", "d", "e"])
        assert sid is not None
        assert len(sh.history[sid]["top_results"]) == 3

    def test_add_search_top_results_none_stored_as_empty_list(self, sh: SearchHistory):
        """Comment 15: top_results가 None이면 빈 리스트([])로 정확히 저장됩니다."""
        sid = sh.add_search("q", 2, top_results=None)
        assert sid is not None
        assert sh.history[sid]["top_results"] == []

    def test_add_search_multiple_returns_unique_ids(self, sh: SearchHistory):
        """여러 번 추가해도 고유한 ID가 생성됩니다."""
        ids = {sh.add_search(f"query_{i}", i) for i in range(5)}
        assert len(ids) == 5

    def test_add_search_rollback_on_save_failure(self, sh: SearchHistory):
        """_save_history가 실패하면 추가가 롤백되고 None이 반환됩니다."""
        with patch.object(sh, "_save_history", return_value=False):
            sid = sh.add_search("rollback test", results_count=1)
        assert sid is None
        assert not sh.history


# ─────────────────────────────────────────────────────────
# get_search 테스트
# ─────────────────────────────────────────────────────────


class TestGetSearch:
    """get_search 메서드를 검증합니다."""

    def test_get_search_returns_record(self, sh: SearchHistory):
        """존재하는 ID로 조회하면 레코드 딕셔너리를 반환합니다."""
        sid = sh.add_search("get test", results_count=3)
        assert sid is not None
        record = sh.get_search(sid)
        assert record is not None
        assert record["query"] == "get test"

    def test_get_search_returns_none_for_missing_id(self, sh: SearchHistory):
        """존재하지 않는 ID는 None을 반환합니다."""
        assert sh.get_search("nonexistent_id") is None

    def test_get_search_refreshes_and_sees_concurrent_writes(
        self, tmp_history_file: str
    ):
        """Comment 9: 다른 인스턴스가 추가한 기록을 쓰기 연산 없이도 get_search 호출 시 동기화하여 읽습니다."""
        sh1 = SearchHistory(storage_path=tmp_history_file)
        sh2 = SearchHistory(storage_path=tmp_history_file)

        sid1 = sh1.add_search("concurrent write", 1)
        assert sid1 is not None

        # sh2는 쓰기를 수행하지 않고 바로 get_search를 호출해도 디스크 최신 상태를 읽어야 함
        record = sh2.get_search(sid1)
        assert record is not None
        assert record["query"] == "concurrent write"

    def test_refresh_clears_history_when_file_is_removed(self, tmp_history_file: str):
        """Comment 5: 저장 파일이 외부에서 삭제된 경우 _refresh_history()는 self.history를 빈 딕셔너리로 초기화합니다."""
        sh_inst = SearchHistory(storage_path=tmp_history_file)
        sid = sh_inst.add_search("will be removed", 1)
        assert sid is not None
        assert sid in sh_inst.history

        # 외부에서 파일 삭제
        os.unlink(tmp_history_file)

        # refresh 실행 시 기존 메모리가 남아있지 않고 비워져야 함
        with sh_inst._interprocess_lock():
            success = sh_inst._refresh_history()
        assert success is True
        assert sh_inst.history == {}


# ─────────────────────────────────────────────────────────
# get_recent_searches 테스트 (limit 슬라이싱 + 최신 항목 검증)
# ─────────────────────────────────────────────────────────


class TestGetRecentSearches:
    """get_recent_searches 메서드의 limit 슬라이싱을 검증합니다."""

    def _add_n(self, sh: SearchHistory, n: int) -> list:
        """n개의 검색 기록을 추가하고 ID 리스트를 반환합니다."""
        return [sh.add_search(f"query_{i}", i) for i in range(n)]

    def test_get_recent_searches_returns_all_when_under_limit(self, sh: SearchHistory):
        """기록 수가 limit보다 적을 때 전체를 반환합니다."""
        self._add_n(sh, 3)
        results = sh.get_recent_searches(limit=10)
        assert len(results) == 3

    def test_get_recent_searches_respects_limit_and_selects_newest(
        self, sh: SearchHistory
    ):
        """기록 수가 limit을 초과할 때 가장 최신 N개를 정확히 반환합니다."""
        self._add_n(sh, 15)
        limit = 5
        results = sh.get_recent_searches(limit=limit)
        assert len(results) == limit

        all_sorted_times = sorted(
            (v["search_time"] for v in sh.history.values()), reverse=True
        )
        expected_top_times = set(all_sorted_times[:limit])
        returned_times = {r["search_time"] for r in results}
        assert returned_times == expected_top_times

    def test_get_recent_searches_sorted_newest_first(self, sh: SearchHistory):
        """반환 목록이 최신순(내림차순)으로 정렬됩니다."""
        self._add_n(sh, 5)
        results = sh.get_recent_searches(limit=5)
        times = [r["search_time"] for r in results]
        assert times == sorted(times, reverse=True)

    def test_get_recent_searches_contains_id_key(self, sh: SearchHistory):
        """반환된 각 항목에 'id' 키가 포함됩니다."""
        self._add_n(sh, 2)
        results = sh.get_recent_searches()
        assert all("id" in r for r in results)

    def test_get_recent_searches_empty_history(self, sh: SearchHistory):
        """히스토리가 없으면 빈 리스트를 반환합니다."""
        assert sh.get_recent_searches() == []

    def test_get_recent_searches_limit_zero(self, sh: SearchHistory):
        """limit=0 이면 빈 리스트를 반환합니다."""
        self._add_n(sh, 3)
        assert sh.get_recent_searches(limit=0) == []


# ─────────────────────────────────────────────────────────
# get_all_searches 테스트 (내용 동등성 검증)
# ─────────────────────────────────────────────────────────


class TestGetAllSearches:
    """get_all_searches 메서드를 검증합니다."""

    def test_get_all_searches_returns_full_history_with_correct_content(
        self, sh: SearchHistory
    ):
        """추가된 모든 기록의 ID와 내용이 반환 딕셔너리와 정확히 일치합니다."""
        sid_a = sh.add_search("alpha", 1)
        sid_b = sh.add_search("beta", 2)
        assert sid_a is not None
        assert sid_b is not None
        all_searches = sh.get_all_searches()

        assert len(all_searches) == 2
        assert sid_a in all_searches
        assert sid_b in all_searches
        assert all_searches[sid_a]["query"] == "alpha"
        assert all_searches[sid_a]["results_count"] == 1
        assert all_searches[sid_b]["query"] == "beta"
        assert all_searches[sid_b]["results_count"] == 2

    def test_get_all_searches_empty(self, sh: SearchHistory):
        """히스토리가 없으면 빈 딕셔너리를 반환합니다."""
        assert sh.get_all_searches() == {}


# ─────────────────────────────────────────────────────────
# delete_search 테스트 (정확한 롤백 스냅샷)
# ─────────────────────────────────────────────────────────


class TestDeleteSearch:
    """delete_search 메서드를 검증합니다."""

    def test_delete_search_removes_record(self, sh: SearchHistory):
        """존재하는 ID 삭제는 True를 반환하고 메모리에서 제거됩니다."""
        sid = sh.add_search("delete me", 1)
        assert sid is not None
        result = sh.delete_search(sid)
        assert result is True
        assert sh.get_search(sid) is None

    def test_delete_search_returns_false_for_missing_id(self, sh: SearchHistory):
        """존재하지 않는 ID 삭제는 False를 반환합니다."""
        assert sh.delete_search("not_a_real_id") is False

    def test_stale_instance_can_delete_concurrently_added_record(
        self, tmp_history_file: str
    ):
        """Comment 10: 인스턴스 생성 이후 다른 프로세스에서 추가한 기록도 delete_search가 디스크 갱신 후 정상 삭제합니다."""
        sh1 = SearchHistory(storage_path=tmp_history_file)
        sh2 = SearchHistory(storage_path=tmp_history_file)

        # sh1이 새로운 레코드 추가
        sid1 = sh1.add_search("added by sh1", 1)
        assert sid1 is not None

        # sh2는 로컬 메모리에 sid1이 없지만, delete_search 호출 시 디스크를 동기화하여 삭제에 성공해야 함
        deleted = sh2.delete_search(sid1)
        assert deleted is True
        assert sh1.get_search(sid1) is None

    def test_deleted_searches_do_not_reappear_on_other_instance_save(
        self, tmp_history_file: str
    ):
        """Comment 4: 한 인스턴스에서 삭제된 기록이 이전 복사본을 쥐고 있던 인스턴스의 추후 저장으로 부활하지 않습니다."""
        sh1 = SearchHistory(storage_path=tmp_history_file)
        sh2 = SearchHistory(storage_path=tmp_history_file)

        id1 = sh1.add_search("search 1", 1)
        assert id1 is not None
        # sh2 동기화
        sh2.get_all_searches()

        # sh1이 search 1 삭제
        assert sh1.delete_search(id1) is True

        # sh2가 새로운 search 2 추가 저장
        id2 = sh2.add_search("search 2", 2)
        assert id2 is not None

        # 디스크 및 sh1/sh2 전체 히스토리에 id1은 영구 삭제되어 없어야 함
        all_s = sh2.get_all_searches()
        assert id1 not in all_s
        assert id2 in all_s


# ─────────────────────────────────────────────────────────
# clear_all 테스트 (정확한 롤백 스냅샷)
# ─────────────────────────────────────────────────────────


class TestClearAll:
    """clear_all 메서드를 검증합니다."""

    def test_clear_all_empties_history(self, sh: SearchHistory):
        """clear_all 후 히스토리가 비워집니다."""
        sh.add_search("a", 1)
        sh.add_search("b", 2)
        result = sh.clear_all()
        assert result is True
        assert not sh.history

    def test_clear_all_rollback_restores_exact_history(self, sh: SearchHistory):
        """Comment 13: _save_history 실패 시 락 내부에서 스냅샷을 복원하여 이전 히스토리가 정확히 유지됩니다."""
        sh.add_search("keep me", 5)
        sh.add_search("also keep", 3)
        snapshot_before = {k: dict(v) for k, v in sh.history.items()}

        with patch.object(sh, "_save_history", return_value=False):
            result = sh.clear_all()

        assert result is False
        assert sh.history == snapshot_before


# ─────────────────────────────────────────────────────────
# get_statistics 테스트 (반올림 회귀 감지)
# ─────────────────────────────────────────────────────────


class TestGetStatistics:
    """get_statistics 메서드를 검증합니다."""

    def test_statistics_empty_history(self, sh: SearchHistory):
        """히스토리가 없을 때 모든 통계가 기본값입니다."""
        stats = sh.get_statistics()
        assert stats["total_searches"] == 0
        assert stats["avg_results"] == 0.0
        assert stats["most_common_query"] is None

    def test_statistics_total_searches(self, sh: SearchHistory):
        """total_searches가 추가된 기록 수와 일치합니다."""
        sh.add_search("x", 1)
        sh.add_search("y", 3)
        stats = sh.get_statistics()
        assert stats["total_searches"] == 2

    def test_statistics_avg_results_rounds_to_one_decimal(self, sh: SearchHistory):
        """avg_results가 소수점 첫째 자리로 반올림됩니다."""
        sh.add_search("a", 1)
        sh.add_search("b", 2)
        sh.add_search("c", 4)
        stats = sh.get_statistics()
        assert stats["avg_results"] == 2.3

    def test_statistics_most_common_query(self, sh: SearchHistory):
        """most_common_query는 가장 많이 등장한 쿼리를 반환합니다."""
        sh.add_search("popular", 1)
        sh.add_search("popular", 2)
        sh.add_search("other", 1)
        stats = sh.get_statistics()
        assert stats["most_common_query"] == "popular"


# ─────────────────────────────────────────────────────────
# 다중 사용자 세션 격리 및 레거시 레코드 테스트 (Comment 3, 5, 13)
# ─────────────────────────────────────────────────────────


class TestMultiUserIsolation:
    """다중 사용자 세션 간 검색 이력 격리를 검증합니다."""

    def test_users_only_see_their_own_searches(self, tmp_history_file: str):
        """Comment 5: user_id가 다른 인스턴스는 동일 파일 내에서도 상대방의 검색을 조회하지 못합니다."""
        sh_alice = SearchHistory(storage_path=tmp_history_file, user_id="alice")
        sh_bob = SearchHistory(storage_path=tmp_history_file, user_id="bob")

        id_a = sh_alice.add_search("alice query", 5)
        id_b = sh_bob.add_search("bob secret query", 2)
        assert id_a is not None
        assert id_b is not None

        # Alice는 Bob의 쿼리를 볼 수 없음
        assert sh_alice.get_search(id_b) is None
        alice_recent = [r["query"] for r in sh_alice.get_recent_searches()]
        assert "alice query" in alice_recent
        assert "bob secret query" not in alice_recent

        # Bob은 Alice의 쿼리를 볼 수 없음
        assert sh_bob.get_search(id_a) is None
        bob_recent = [r["query"] for r in sh_bob.get_recent_searches()]
        assert "bob secret query" in bob_recent
        assert "alice query" not in bob_recent

    def test_user_clear_all_only_deletes_own_records(self, tmp_history_file: str):
        """Comment 5: user_id가 설정된 상태에서 clear_all 호출 시 다른 사용자의 기록은 보존됩니다."""
        sh_alice = SearchHistory(storage_path=tmp_history_file, user_id="alice")
        sh_bob = SearchHistory(storage_path=tmp_history_file, user_id="bob")

        id_a = sh_alice.add_search("alice query", 1)
        id_b = sh_bob.add_search("bob query", 1)

        # Alice가 전체 삭제
        assert sh_alice.clear_all() is True

        # Alice의 기록은 비워짐
        assert sh_alice.get_all_searches() == {}
        # Bob의 기록은 건재함
        assert id_b in sh_bob.get_all_searches()

    def test_per_user_pruning_does_not_affect_other_users(self, tmp_history_file: str):
        """Comment 3: user_id가 설정된 경우 해당 사용자의 레코드만 프루닝되며 타 사용자의 기록은 유지됩니다."""
        sh_alice = SearchHistory(
            storage_path=tmp_history_file, user_id="alice", max_history_entries=2
        )
        sh_bob = SearchHistory(
            storage_path=tmp_history_file, user_id="bob", max_history_entries=2
        )

        # Bob이 2개 기록 작성
        b1 = sh_bob.add_search("bob 1", 1)
        b2 = sh_bob.add_search("bob 2", 2)

        # Alice가 3개 기록 작성하여 Alice의 첫 기록이 프루닝되도록 유도
        a1 = sh_alice.add_search("alice 1", 1)
        a2 = sh_alice.add_search("alice 2", 2)
        a3 = sh_alice.add_search("alice 3", 3)

        # Bob의 레코드는 2개 모두 그대로 남아있어야 함
        bob_searches = sh_bob.get_all_searches()
        assert b1 in bob_searches
        assert b2 in bob_searches

        # Alice의 레코드는 2개로 프루닝되어 a1은 삭제되고 a2, a3만 유지되어야 함
        alice_searches = sh_alice.get_all_searches()
        assert len(alice_searches) == 2
        assert a1 not in alice_searches
        assert a2 in alice_searches
        assert a3 in alice_searches

    def test_legacy_records_without_user_id_hidden_from_scoped_users(
        self, tmp_history_file: str
    ):
        """Comment 13: user_id 필드가 없는 레거시 레코드는 user_id가 지정된 인스턴스에 노출되지 않습니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        seed = {
            "search_legacy_01": {
                "query": "legacy query",
                "results_count": 10,
                "top_results": [],
                "search_time": "2025-01-01T10:00:00",
                "created_at": "2025-01-01 10:00:00",
                # "user_id" 필드 없음
            }
        }
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            json.dump(seed, f)

        sh_alice = SearchHistory(storage_path=tmp_history_file, user_id="alice")
        assert sh_alice.get_search("search_legacy_01") is None
        assert "search_legacy_01" not in sh_alice.get_all_searches()
        assert not any(
            r["id"] == "search_legacy_01" for r in sh_alice.get_recent_searches()
        )

        # 반면 user_id=None 인 레거시/글로벌 인스턴스는 레거시 레코드를 조회할 수 있음
        sh_global = SearchHistory(storage_path=tmp_history_file, user_id=None)
        assert sh_global.get_search("search_legacy_01") is not None


# ─────────────────────────────────────────────────────────
# 보안 및 파일 I/O 견고성 테스트 (Comment 1, 4, 8, 10, 11, 14, 16)
# ─────────────────────────────────────────────────────────


class TestSaveHistoryRobustness:
    """심볼릭 링크 탈출 방어, 파일 손상 방지, 권한 제어 등 보안 및 견고성을 검증합니다."""

    def test_symlink_pointing_outside_trusted_dir_is_rejected(self, tmp_path: Path):
        """Comment 1 & 14: 신뢰할 수 있는 디렉터리 외부를 가리키는 심볼릭 링크를 통한 쓰기는 거부되며 외부 파일은 변경되지 않습니다."""
        outside_dir = tmp_path / "outside"
        trusted_dir = tmp_path / "trusted"
        outside_dir.mkdir()
        trusted_dir.mkdir()

        malicious_target = outside_dir / "target.json"
        initial_content = '{"sensitive": "data"}'
        malicious_target.write_text(initial_content, encoding="utf-8")

        symlink_path = trusted_dir / "link.json"
        os.symlink(malicious_target, symlink_path)

        # Comment 14: _validate_and_resolve_storage_path()를 직접 호출하는 대신 add_search를 시도
        sh_bad = SearchHistory(
            storage_path=str(symlink_path), trusted_base_dir=str(trusted_dir)
        )
        result = sh_bad.add_search("malicious query", 1)

        # 쓰기가 차단되어 None이 반환되어야 함
        assert result is None
        # 외부 타깃 파일의 내용이 손상되거나 변경되지 않아야 함
        assert malicious_target.read_text(encoding="utf-8") == initial_content

    def test_parent_directory_symlink_pointing_outside_is_rejected(
        self, tmp_path: Path
    ):
        """Comment 1: 부모 디렉터리 자체가 외부를 가리키는 심볼릭 링크인 경우에도 거부됩니다."""
        outside_dir = tmp_path / "outside"
        trusted_dir = tmp_path / "trusted"
        outside_dir.mkdir()
        trusted_dir.mkdir()

        # trusted_dir 안에 outside_dir를 가리키는 symlink 디렉터리 생성
        symlinked_dir = trusted_dir / "linked_parent"
        os.symlink(outside_dir, symlinked_dir)

        target_file = symlinked_dir / "history.json"
        sh = SearchHistory(
            storage_path=str(target_file), trusted_base_dir=str(trusted_dir)
        )
        result = sh.add_search("test", 1)
        assert result is None

    def test_symlink_inside_trusted_dir_is_safely_resolved(self, tmp_path: Path):
        """Comment 1: 신뢰할 수 있는 디렉터리 내부를 가리키는 심볼릭 링크는 안전하게 해석됩니다."""
        trusted_dir = tmp_path / "data"
        trusted_dir.mkdir()

        real_file = trusted_dir / "real.json"
        real_file.write_text("{}", encoding="utf-8")

        symlink_path = trusted_dir / "link.json"
        os.symlink(real_file, symlink_path)

        sh = SearchHistory(
            storage_path=str(symlink_path), trusted_base_dir=str(trusted_dir)
        )
        sid = sh.add_search("safe symlink", 1)
        assert sid is not None
        assert os.path.islink(str(symlink_path))
        # 실제 타깃 파일에 기록되었는지 검증
        with open(real_file, encoding="utf-8") as f:
            data = json.load(f)
        assert sid in data

    def test_failed_save_never_truncates_existing_history(self, sh: SearchHistory):
        """저장 실패 시 기존 파일이 0바이트로 truncate되거나 손상되지 않습니다."""
        sid = sh.add_search("important search", 10)
        assert sid is not None

        with open(sh.storage_path, encoding="utf-8") as f:
            original_content = f.read()

        # 쓰기 중단 시뮬레이션
        with patch("tempfile.NamedTemporaryFile", side_effect=OSError("disk full")):
            result = sh._save_history()

        assert result is False
        with open(sh.storage_path, encoding="utf-8") as f:
            after_content = f.read()
        assert after_content == original_content

    def test_history_file_always_enforces_0o600_permissions(self, tmp_path: Path):
        """Comment 8: 신규 파일뿐만 아니라 기존 파일이 0o644이더라도 항상 0o600으로 강화됩니다."""
        history_file = tmp_path / "permission_test.json"
        history_file.write_text("{}", encoding="utf-8")
        os.chmod(str(history_file), 0o644)

        sh = SearchHistory(storage_path=str(history_file))
        sh.add_search("tighten permissions", 1)

        file_mode = stat.S_IMODE(os.stat(str(history_file)).st_mode)
        assert file_mode == 0o600

    def test_save_history_calls_fsync(self, tmp_history_file: str):
        """Comment 10: 저장 시 임시 파일 및 디렉터리에 fsync를 호출하여 충돌 내구성을 보장합니다."""
        sh = SearchHistory(storage_path=tmp_history_file)
        with patch("os.fsync") as mock_fsync:
            sid = sh.add_search("fsync test", 1)
            assert sid is not None
            assert mock_fsync.called

    def test_failed_save_restores_pruned_records_via_actual_prune(
        self, tmp_history_file: str
    ):
        """Comment 16: _save_history를 모킹하지 않고 NamedTemporaryFile에서 실패하게 하여 실제 프루닝 후 롤백을 검증합니다."""
        sh = SearchHistory(storage_path=tmp_history_file, max_history_entries=2)
        sh.add_search("item 1", 1)
        sh.add_search("item 2", 2)
        assert len(sh.history) == 2

        # _save_history 내부의 NamedTemporaryFile 단계에서 실패하도록 모킹
        # 이를 통해 _prune_history()가 실제로 실행된 후 저장 실패로 복원되는지 확인
        with patch(
            "tempfile.NamedTemporaryFile",
            side_effect=OSError("simulated write failure"),
        ):
            sid3 = sh.add_search("item 3", 3)

        assert sid3 is None
        # 저장 실패 시 프루닝으로 제거될 뻔했던 item 1과 item 2가 온전히 복원되어 있어야 함
        assert len(sh.history) == 2
        queries = [v["query"] for v in sh.history.values()]
        assert "item 1" in queries
        assert "item 2" in queries

    def test_flock_timeout_raises_timeout_error(self, tmp_history_file: str):
        """Comment 11: 락 획득 시 타임아웃 발생 시 TimeoutError가 발생합니다."""
        sh = SearchHistory(storage_path=tmp_history_file)

        # 락 대기 시 항상 BlockingIOError(EWOULDBLOCK)가 발생하도록 모킹
        blocking_err = OSError()
        blocking_err.errno = 35  # EWOULDBLOCK (macOS/Linux)

        with patch("backend.search_history._FLOCK_TIMEOUT_SECONDS", 0.05):
            with patch("fcntl.flock", side_effect=blocking_err):
                with pytest.raises(TimeoutError, match="타임아웃"):
                    with sh._interprocess_lock():
                        pass

    def test_no_fcntl_fails_closed(self, tmp_history_file: str):
        """Comment 4 & 9: HAS_FCNTL이 False인 환경에서는 락 획득 시 RuntimeError가 발생하며 조용히 통과하지 않습니다."""
        sh = SearchHistory(storage_path=tmp_history_file)
        with patch("backend.search_history.HAS_FCNTL", False):
            with pytest.raises(RuntimeError, match="fcntl을 사용할 수 없는 플랫폼"):
                with sh._interprocess_lock():
                    pass


# ─────────────────────────────────────────────────────────
# _custom_json_serializer 테스트
# ─────────────────────────────────────────────────────────


class TestCustomJsonSerializer:
    """_custom_json_serializer 헬퍼를 검증합니다."""

    def test_serializes_datetime(self):
        """datetime 객체가 ISO 8601 문자열로 변환됩니다."""
        from datetime import datetime

        dt = datetime(2026, 1, 15, 12, 30, 45)
        result = _custom_json_serializer(dt)
        assert result == "2026-01-15T12:30:45"

    def test_serializes_date(self):
        """date 객체가 ISO 8601 문자열로 변환됩니다."""
        from datetime import date

        d = date(2026, 6, 1)
        result = _custom_json_serializer(d)
        assert result == "2026-06-01"

    def test_raises_type_error_for_unserializable(self):
        """직렬화 불가 타입에 TypeError가 발생합니다."""
        with pytest.raises(TypeError):
            _custom_json_serializer(object())

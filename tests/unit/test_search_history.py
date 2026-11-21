# tests/unit/test_search_history.py

"""
[KO] backend/search_history.py SearchHistory에 대한 단위 테스트.
[EN] Unit tests for SearchHistory in backend/search_history.py.

테스트 범위:
- 파일 I/O 실패 시 격리 (mocking) + 원자적 쓰기 검증
- 손상된 데이터(JSON 파싱 오류, dict 미준수, malformed record) 복원력 + 경고 로그 발생 검증
- 검색 기록 최대 보관 수(limit) 슬라이싱 + 최신 항목 선택 검증
- add_search / get_search / get_recent_searches / get_all_searches 내용 검증
- delete_search / clear_all 삭제 및 정확한 롤백 스냅샷 검증
- _apply_and_persist 롤백 패턴 (정확한 히스토리 동등성)
- get_statistics 반올림 회귀 감지
- 5·6차 리뷰 전방위 대응 검증:
  - 심볼릭 링크 상위 컴포넌트 검증 및 탈출 시 락 파일 미생성 검증 (Comment 1, 3)
  - fcntl 미지원 시 읽기 허용 및 쓰기 fail-closed 검증 (Comment 9)
  - 락 타임아웃 시 add_search 계약 준수(None 반환) 및 플랫폼 무관 errno.EWOULDBLOCK 검증 (Comment 10, 11)
  - 임시 파일 및 디렉터리 모두에 대한 fsync 이중 호출 검증 및 디렉터리 fsync 실패 시 저장 실패 처리 (Comment 5, 13)
  - per-user 프루닝 및 공유 히스토리 전체 상한(bounded history) 검증 (Comment 7, 12)
  - 프루닝 저장 실패 시 로드/갱신 실패 전파 검증 (Comment 6)
  - 갱신 실패 시 stale 캐시 노출 방지 검증 (Comment 4)
  - Malformed record 방어 검증 (Comment 8)
  - 필드 타입이 잘못된 persisted record 제거 및 fcntl 미지원 읽기 무쓰기 검증
  - 암묵적 경로 신뢰 기준의 심볼릭 링크 차단 및 조회 락 타임아웃 기본값 검증
"""

import errno
import json
import logging
import os
import stat
from datetime import date, datetime
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
        """0 또는 음수 max_history_entries 설정 시 ValueError가 발생합니다."""
        with pytest.raises(ValueError, match="positive integer"):
            SearchHistory(storage_path=tmp_history_file, max_history_entries=0)

        with pytest.raises(ValueError, match="positive integer"):
            SearchHistory(storage_path=tmp_history_file, max_history_entries=-5)

    def test_init_rejects_non_int_max_history_entries(self, tmp_history_file: str):
        """float 또는 bool 등 non-int 전달 시 TypeError가 발생합니다."""
        with pytest.raises(TypeError, match="plain int"):
            SearchHistory(storage_path=tmp_history_file, max_history_entries=2.5)  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="plain int"):
            SearchHistory(storage_path=tmp_history_file, max_history_entries=True)  # type: ignore[arg-type]

    def test_init_logs_warning_when_user_id_is_none(
        self, tmp_history_file: str, caplog: pytest.LogCaptureFixture
    ):
        """user_id=None 으로 초기화 시 공유 파일 보안 경고 로그가 기록됩니다."""
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
        """로드 시 max_history_entries를 초과하는 기록이 있으면 즉시 프루닝하고 파일에도 저장합니다."""
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
        """JSON 최상위가 dict가 아닌 배열/리스트인 경우 빈 히스토리로 폴백되고 경고가 기록됩니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            json.dump(["not", "a", "dict"], f)

        with caplog.at_level(logging.WARNING, logger="backend.search_history"):
            sh = SearchHistory(storage_path=tmp_history_file)

        assert sh.history == {}
        assert any("dict가 아닌 타입" in record.message for record in caplog.records)

    def test_load_history_ignores_malformed_records(self, tmp_history_file: str):
        """Comment 8: 레코드 값이 None이나 문자열 등 dict가 아닌 malformed 항목이 섞여 있어도 정상 로드됩니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        seed = {
            "valid_record": {
                "query": "valid",
                "results_count": 1,
                "search_time": "2026-01-01T12:00:00",
                "created_at": "2026-01-01 12:00:00",
                "user_id": "alice",
            },
            "invalid_none": None,
            "invalid_string": "corrupted",
            "invalid_list": [1, 2, 3],
        }
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            json.dump(seed, f)

        sh = SearchHistory(storage_path=tmp_history_file, user_id="alice")
        assert "valid_record" in sh.history
        assert "invalid_none" not in sh.history
        assert len(sh.get_all_searches()) == 1

    def test_load_history_rejects_records_with_invalid_field_types(
        self, tmp_history_file: str
    ):
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        seed = {
            "valid": {"query": "ok", "results_count": 2},
            "invalid_query": {"query": [], "results_count": 1},
            "invalid_count": {"query": "bad", "results_count": "1"},
            "invalid_boolean_count": {"query": "bad", "results_count": True},
            "invalid_top_results": {
                "query": "bad",
                "results_count": 1,
                "top_results": [None],
            },
        }
        with open(tmp_history_file, "w", encoding="utf-8") as history_file:
            json.dump(seed, history_file)

        history = SearchHistory(storage_path=tmp_history_file)

        assert list(history.history) == ["valid"]
        assert history.get_statistics()["avg_results"] == 2.0
        with open(tmp_history_file, "r", encoding="utf-8") as history_file:
            assert list(json.load(history_file)) == ["valid"]


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
        """top_results가 None이면 빈 리스트([])로 정확히 저장됩니다."""
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

    def test_add_search_returns_none_on_lock_timeout(self, sh: SearchHistory):
        """Comment 10: 락 타임아웃 발생 시 예외를 던지지 않고 계약대로 None을 반환합니다."""
        with patch.object(
            sh, "_interprocess_lock", side_effect=TimeoutError("lock timeout")
        ):
            sid = sh.add_search("timeout test", 1)
        assert sid is None


# ─────────────────────────────────────────────────────────
# get_search / get_recent_searches / get_all_searches 테스트
# ─────────────────────────────────────────────────────────


class TestGetSearch:
    """조회 메서드 및 stale 데이터 방어 검증."""

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
        """다른 인스턴스가 추가한 기록을 쓰기 연산 없이도 get_search 호출 시 동기화하여 읽습니다."""
        sh1 = SearchHistory(storage_path=tmp_history_file)
        sh2 = SearchHistory(storage_path=tmp_history_file)

        sid1 = sh1.add_search("concurrent write", 1)
        assert sid1 is not None

        record = sh2.get_search(sid1)
        assert record is not None
        assert record["query"] == "concurrent write"

    def test_refresh_failure_prevents_stale_data_exposure(self, tmp_history_file: str):
        """Comment 4: _refresh_history() 실패 시 이전 메모리 캐시(stale records)를 노출하지 않고 None/빈 결과를 반환합니다."""
        sh_inst = SearchHistory(storage_path=tmp_history_file)
        sid = sh_inst.add_search("initial query", 1)
        assert sid is not None

        with patch.object(sh_inst, "_refresh_history", return_value=False):
            assert sh_inst.get_search(sid) is None
            assert sh_inst.get_recent_searches() == []
            assert sh_inst.get_all_searches() == {}
            stats = sh_inst.get_statistics()
            assert stats["total_searches"] == 0

    def test_refresh_clears_history_when_file_is_removed(self, tmp_history_file: str):
        """저장 파일이 외부에서 삭제된 경우 _refresh_history()는 self.history를 빈 딕셔너리로 초기화합니다."""
        sh_inst = SearchHistory(storage_path=tmp_history_file)
        sid = sh_inst.add_search("will be removed", 1)
        assert sid is not None
        assert sid in sh_inst.history

        os.unlink(tmp_history_file)

        with sh_inst._interprocess_lock(write=False):
            success = sh_inst._refresh_history()
        assert success is True
        assert sh_inst.history == {}


# ─────────────────────────────────────────────────────────
# get_recent_searches & get_all_searches 슬라이싱 검증
# ─────────────────────────────────────────────────────────


class TestGetRecentAndAllSearches:
    """get_recent_searches 및 get_all_searches의 세부 동작을 검증합니다."""

    def _add_n(self, sh: SearchHistory, n: int) -> list:
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
            (v["search_time"] for v in sh.history.values() if isinstance(v, dict)),
            reverse=True,
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

    def test_get_all_searches_returns_full_history(self, sh: SearchHistory):
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
        assert all_searches[sid_b]["query"] == "beta"


# ─────────────────────────────────────────────────────────
# delete_search / clear_all 테스트
# ─────────────────────────────────────────────────────────


class TestDeleteAndClear:
    """삭제 및 전체 초기화 메서드를 검증합니다."""

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

    def test_clear_all_empties_history(self, sh: SearchHistory):
        """clear_all 후 히스토리가 비워집니다."""
        sh.add_search("a", 1)
        sh.add_search("b", 2)
        result = sh.clear_all()
        assert result is True
        assert not sh.history

    def test_clear_all_rollback_restores_exact_history(self, sh: SearchHistory):
        """_save_history 실패 시 락 내부에서 스냅샷을 복원하여 이전 히스토리가 정확히 유지됩니다."""
        sh.add_search("keep me", 5)
        sh.add_search("also keep", 3)
        snapshot_before = {
            k: dict(v) for k, v in sh.history.items() if isinstance(v, dict)
        }

        with patch.object(sh, "_save_history", return_value=False):
            result = sh.clear_all()

        assert result is False
        assert sh.history == snapshot_before


# ─────────────────────────────────────────────────────────
# get_statistics 테스트
# ─────────────────────────────────────────────────────────


class TestGetStatistics:
    """get_statistics 메서드를 검증합니다."""

    def test_statistics_empty_history(self, sh: SearchHistory):
        """히스토리가 없을 때 모든 통계가 기본값입니다."""
        stats = sh.get_statistics()
        assert stats["total_searches"] == 0
        assert stats["avg_results"] == 0.0
        assert stats["most_common_query"] is None

    def test_statistics_total_searches_and_avg(self, sh: SearchHistory):
        """total_searches 및 avg_results가 올바르게 계산 및 반올림됩니다."""
        sh.add_search("a", 1)
        sh.add_search("b", 2)
        sh.add_search("c", 4)
        stats = sh.get_statistics()
        assert stats["total_searches"] == 3
        assert stats["avg_results"] == 2.3

    def test_statistics_most_common_query(self, sh: SearchHistory):
        """most_common_query는 가장 많이 등장한 쿼리를 반환합니다."""
        sh.add_search("popular", 1)
        sh.add_search("popular", 2)
        sh.add_search("other", 1)
        stats = sh.get_statistics()
        assert stats["most_common_query"] == "popular"


# ─────────────────────────────────────────────────────────
# 다중 사용자 세션 격리 및 전체 상한(bounded history) 테스트
# ─────────────────────────────────────────────────────────


class TestMultiUserIsolationAndBound:
    """다중 사용자 격리 및 디스크 고갈 방지 전체 상한을 검증합니다."""

    def test_users_only_see_their_own_searches(self, tmp_history_file: str):
        """user_id가 다른 인스턴스는 동일 파일 내에서도 상대방의 검색을 조회하지 못합니다."""
        sh_alice = SearchHistory(storage_path=tmp_history_file, user_id="alice")
        sh_bob = SearchHistory(storage_path=tmp_history_file, user_id="bob")

        id_a = sh_alice.add_search("alice query", 5)
        id_b = sh_bob.add_search("bob secret query", 2)
        assert id_a is not None
        assert id_b is not None

        assert sh_alice.get_search(id_b) is None
        alice_recent = [r["query"] for r in sh_alice.get_recent_searches()]
        assert "alice query" in alice_recent
        assert "bob secret query" not in alice_recent

        assert sh_bob.get_search(id_a) is None
        bob_recent = [r["query"] for r in sh_bob.get_recent_searches()]
        assert "bob secret query" in bob_recent
        assert "alice query" not in bob_recent

    def test_user_clear_all_only_deletes_own_records(self, tmp_history_file: str):
        """user_id가 설정된 상태에서 clear_all 호출 시 다른 사용자의 기록은 보존됩니다."""
        sh_alice = SearchHistory(storage_path=tmp_history_file, user_id="alice")
        sh_bob = SearchHistory(storage_path=tmp_history_file, user_id="bob")

        id_a = sh_alice.add_search("alice query", 1)
        id_b = sh_bob.add_search("bob query", 1)

        assert sh_alice.clear_all() is True
        assert sh_alice.get_all_searches() == {}
        assert id_b in sh_bob.get_all_searches()

    def test_shared_history_bounds_total_entries(self, tmp_history_file: str):
        """Comment 7: 많은 유저가 공유 파일에 기록하더라도 global_max를 초과하지 않도록 전체 상한이 적용됩니다."""
        sh_admin = SearchHistory(storage_path=tmp_history_file, max_history_entries=2)

        for u in range(8):
            user_inst = SearchHistory(
                storage_path=tmp_history_file,
                user_id=f"user_{u}",
                max_history_entries=2,
            )
            user_inst.add_search(f"q_{u}_1", 1)
            user_inst.add_search(f"q_{u}_2", 2)

        all_records = sh_admin.get_all_searches()
        assert len(all_records) <= 10


# ─────────────────────────────────────────────────────────
# 보안 및 견고성 테스트 (심볼릭 링크, 락 파일, fsync, fcntl 등)
# ─────────────────────────────────────────────────────────


class TestSecurityAndRobustness:
    """보안 및 견고성을 검증합니다."""

    def test_rejected_path_does_not_create_external_lock_file(self, tmp_path: Path):
        """Comment 3: 신뢰할 수 없는 심볼릭 링크 경로는 락 파일을 외부 디렉터리에 생성하지 않고 즉시 거부됩니다."""
        outside_dir = tmp_path / "outside"
        trusted_dir = tmp_path / "trusted"
        outside_dir.mkdir()
        trusted_dir.mkdir()

        malicious_target = outside_dir / "target.json"
        malicious_target.write_text("{}", encoding="utf-8")

        symlink_path = trusted_dir / "link.json"
        os.symlink(malicious_target, symlink_path)

        sh_bad = SearchHistory(
            storage_path=str(symlink_path), trusted_base_dir=str(trusted_dir)
        )
        result = sh_bad.add_search("blocked", 1)
        assert result is None

        assert not (outside_dir / "target.json.lock").exists()

    def test_inferred_trust_root_cannot_be_a_symlink(self, tmp_path: Path):
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        target_file = outside_dir / "history.json"
        target_file.write_text("{}", encoding="utf-8")
        linked_parent = tmp_path / "linked-parent"
        os.symlink(outside_dir, linked_parent)
        storage_path = linked_parent / "history.json"

        history = SearchHistory(storage_path=str(storage_path))

        assert history.add_search("must be rejected", 1) is None
        assert not (outside_dir / "history.json.lock").exists()
        assert json.loads(target_file.read_text(encoding="utf-8")) == {}

    def test_save_history_calls_both_file_and_directory_fsync(
        self, tmp_history_file: str
    ):
        """Comment 13: 임시 파일과 디렉터리 디스크립터 모두에 대해 fsync가 호출되는지 검증합니다."""
        sh = SearchHistory(storage_path=tmp_history_file)
        with patch("os.fsync") as mock_fsync:
            sid = sh.add_search("fsync dual check", 1)
            assert sid is not None
            assert mock_fsync.call_count >= 2

    def test_failed_directory_fsync_reports_save_failure(self, tmp_history_file: str):
        """Comment 5: 디렉터리 fsync 실패 시 조용히 넘기지 않고 False를 반환하여 저장 실패를 전파합니다."""
        sh = SearchHistory(storage_path=tmp_history_file)

        original_fsync = os.fsync
        call_tracker = {"count": 0}

        def mock_fsync_second_fails(fd):
            call_tracker["count"] += 1
            if call_tracker["count"] >= 2:
                raise OSError("directory sync I/O error")
            original_fsync(fd)

        with patch("os.fsync", side_effect=mock_fsync_second_fails):
            result = sh.add_search("should fail dir sync", 1)
            assert result is None

    def test_pruned_records_save_failure_propagates_error(self, tmp_history_file: str):
        """Comment 6: 갱신 중 프루닝이 발생했으나 저장에 실패한 경우 _refresh_history는 False를 반환합니다."""
        sh = SearchHistory(storage_path=tmp_history_file, max_history_entries=2)
        sh.add_search("item 1", 1)
        sh.add_search("item 2", 2)

        with patch.object(sh, "_prune_history", return_value=True):
            with patch.object(sh, "_save_history", return_value=False):
                with sh._interprocess_lock(write=False):
                    assert sh._refresh_history() is False

    def test_flock_timeout_uses_platform_ewouldblock(self, tmp_history_file: str):
        """Comment 11: 락 타임아웃 테스트가 Linux(11)와 macOS(35) 모두에서 errno.EWOULDBLOCK을 사용합니다."""
        sh = SearchHistory(storage_path=tmp_history_file)

        blocking_err = OSError()
        blocking_err.errno = errno.EWOULDBLOCK

        with patch("backend.search_history._FLOCK_TIMEOUT_SECONDS", 0.05):
            with patch("fcntl.flock", side_effect=blocking_err):
                with pytest.raises(TimeoutError, match="타임아웃"):
                    with sh._interprocess_lock(write=True):
                        pass

    def test_no_fcntl_allows_read_but_denies_write(self, tmp_history_file: str):
        """Comment 9: fcntl이 없는 환경에서도 초기화 및 읽기는 가능하고 쓰기 연산은 실패(Fail-closed)합니다."""
        with patch("backend.search_history.HAS_FCNTL", False):
            sh_no_fcntl = SearchHistory(storage_path=tmp_history_file)
            assert sh_no_fcntl.get_all_searches() == {}
            assert sh_no_fcntl.get_recent_searches() == []
            assert not os.path.exists(os.path.dirname(tmp_history_file))

            sid = sh_no_fcntl.add_search("will fail", 1)
            assert sid is None

    def test_no_fcntl_read_pruning_does_not_write_to_disk(self, tmp_history_file: str):
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        seed = {
            f"search_{index}": {
                "query": f"query {index}",
                "results_count": index,
                "search_time": f"2026-01-01T00:00:0{index}",
            }
            for index in range(2)
        }
        with open(tmp_history_file, "w", encoding="utf-8") as history_file:
            json.dump(seed, history_file)

        with patch("backend.search_history.HAS_FCNTL", False):
            history = SearchHistory(
                storage_path=tmp_history_file, max_history_entries=1
            )
            assert len(history.history) == 1
            assert len(history.get_all_searches()) == 1

        with open(tmp_history_file, "r", encoding="utf-8") as history_file:
            assert len(json.load(history_file)) == 2

    def test_read_apis_return_defaults_on_lock_timeout(self, sh: SearchHistory):
        with patch.object(
            sh, "_interprocess_lock", side_effect=TimeoutError("lock timeout")
        ):
            assert sh.get_search("missing") is None
            assert sh.get_recent_searches() == []
            assert sh.get_all_searches() == {}
            assert sh.get_statistics() == {
                "total_searches": 0,
                "avg_results": 0.0,
                "most_common_query": None,
            }
            assert sh.delete_search("missing") is False

    def test_history_file_always_enforces_0o600_permissions(self, tmp_path: Path):
        """신규 및 기존 파일 모두 항상 0o600으로 강화됩니다."""
        history_file = tmp_path / "permission_test.json"
        history_file.write_text("{}", encoding="utf-8")
        os.chmod(str(history_file), 0o644)

        sh = SearchHistory(storage_path=str(history_file))
        sh.add_search("tighten permissions", 1)

        file_mode = stat.S_IMODE(os.stat(str(history_file)).st_mode)
        assert file_mode == 0o600


# ─────────────────────────────────────────────────────────
# _custom_json_serializer 테스트
# ─────────────────────────────────────────────────────────


class TestCustomJsonSerializer:
    """_custom_json_serializer 헬퍼를 검증합니다."""

    def test_serializes_datetime(self):
        """datetime 객체가 ISO 8601 문자열로 변환됩니다."""
        dt = datetime(2026, 1, 15, 12, 30, 45)
        result = _custom_json_serializer(dt)
        assert result == "2026-01-15T12:30:45"

    def test_serializes_date(self):
        """date 객체가 ISO 8601 문자열로 변환됩니다."""
        d = date(2026, 6, 1)
        result = _custom_json_serializer(d)
        assert result == "2026-06-01"

    def test_raises_type_error_for_unserializable(self):
        """직렬화 불가 타입에 TypeError가 발생합니다."""
        with pytest.raises(TypeError):
            _custom_json_serializer(object())

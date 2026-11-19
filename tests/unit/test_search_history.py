# tests/unit/test_search_history.py

"""
[KO] backend/search_history.py SearchHistory에 대한 단위 테스트.
[EN] Unit tests for SearchHistory in backend/search_history.py.

테스트 범위:
- 파일 I/O 실패 시 격리 (mocking) + 원자적 쓰기 검증
- 손상된 데이터(JSON 파싱 오류) 복원력 + 경고 로그 발생 검증
- 검색 기록 최대 보관 수(limit) 슬라이싱 + 최신 항목 선택 검증
- add_search / get_search / get_recent_searches / get_all_searches 내용 검증
- delete_search / clear_all 삭제 및 정확한 롤백 스냅샷 검증
- _apply_and_persist 롤백 패턴 (정확한 히스토리 동등성)
- get_statistics 반올림 회귀 감지
"""

import json
import logging
import os
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
        assert sh.history == {}

    def test_init_creates_data_directory_when_absent(self, tmp_path: Path):
        """부모 디렉터리가 없어도 자동 생성됩니다."""
        storage = str(tmp_path / "nested" / "dir" / "history.json")
        sh = SearchHistory(storage_path=storage)
        assert sh.history == {}
        assert os.path.isdir(str(tmp_path / "nested" / "dir"))

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

    def test_load_history_falls_back_to_empty_on_corrupt_json(
        self, tmp_history_file: str, caplog: pytest.LogCaptureFixture
    ):
        """손상된 JSON 파일이 있을 때 빈 히스토리로 폴백되고 경고 로그가 발생합니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            f.write("{corrupt: json,,}")

        with caplog.at_level(logging.WARNING, logger="backend.search_history"):
            sh = SearchHistory(storage_path=tmp_history_file)

        # 빈 히스토리 폴백
        assert sh.history == {}
        # 경고 로그 발생 여부 (Comment 4: 운영자 진단 경고 보장)
        assert any("히스토리 로드 실패" in record.message for record in caplog.records)

    def test_load_history_falls_back_to_empty_on_oserror(self, tmp_history_file: str):
        """파일 읽기 중 OSError가 발생하면 빈 히스토리로 폴백됩니다."""
        os.makedirs(os.path.dirname(tmp_history_file), exist_ok=True)
        with open(tmp_history_file, "w", encoding="utf-8") as f:
            json.dump({}, f)

        sh = SearchHistory.__new__(SearchHistory)
        sh.storage_path = tmp_history_file
        sh.history = {}
        with patch("builtins.open", side_effect=OSError("mock read failure")):
            sh._load_history()
        assert sh.history == {}


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
        """top_results가 None이면 빈 리스트로 저장됩니다."""
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
        assert sh.history == {}


# ─────────────────────────────────────────────────────────
# get_search 테스트
# ─────────────────────────────────────────────────────────


class TestGetSearch:
    """get_search 메서드를 검증합니다."""

    def test_get_search_returns_record(self, sh: SearchHistory):
        """존재하는 ID로 조회하면 레코드 딕셔너리를 반환합니다."""
        sid = sh.add_search("get test", results_count=3)
        record = sh.get_search(sid)
        assert record is not None
        assert record["query"] == "get test"

    def test_get_search_returns_none_for_missing_id(self, sh: SearchHistory):
        """존재하지 않는 ID는 None을 반환합니다."""
        assert sh.get_search("nonexistent_id") is None


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
        """기록 수가 limit을 초과할 때 가장 최신 N개를 정확히 반환합니다.
        (Comment 3: 개수 뿐 아니라 최신 항목인지 검증)
        """
        self._add_n(sh, 15)
        limit = 5
        results = sh.get_recent_searches(limit=limit)
        assert len(results) == limit

        # 전체 히스토리를 최신순 정렬했을 때 상위 limit개 search_time과 일치해야 합니다
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
        """추가된 모든 기록의 ID와 내용이 반환 딕셔너리와 정확히 일치합니다.
        (Comment 6: 개수뿐 아니라 키와 레코드 내용까지 검증)
        """
        sid_a = sh.add_search("alpha", 1)
        sid_b = sh.add_search("beta", 2)
        all_searches = sh.get_all_searches()

        # 개수
        assert len(all_searches) == 2
        # 키 존재
        assert sid_a in all_searches
        assert sid_b in all_searches
        # 레코드 내용
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
        result = sh.delete_search(sid)
        assert result is True
        assert sh.get_search(sid) is None

    def test_delete_search_returns_false_for_missing_id(self, sh: SearchHistory):
        """존재하지 않는 ID 삭제는 False를 반환합니다."""
        assert sh.delete_search("not_a_real_id") is False

    def test_delete_search_rollback_restores_exact_history(self, sh: SearchHistory):
        """_save_history 실패 시 삭제가 롤백되고 히스토리가 정확히 복원됩니다.
        (Comment 2: 존재 여부 뿐 아니라 전체 히스토리 동등성 검증)
        """
        sid = sh.add_search("rollback delete", 2)
        assert sid is not None
        # 롤백 전 히스토리 스냅샷 (깊은 복사)
        snapshot_before = {k: dict(v) for k, v in sh.history.items()}

        with patch.object(sh, "_save_history", return_value=False):
            result = sh.delete_search(sid)

        assert result is False
        # 정확한 히스토리 동등성 (키, 레코드 내용 모두 일치)
        assert sh.history == snapshot_before


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
        assert sh.history == {}

    def test_clear_all_rollback_restores_exact_history(self, sh: SearchHistory):
        """_save_history 실패 시 이전 히스토리가 정확히 복원됩니다.
        (Comment 2: 개수뿐 아니라 전체 히스토리 동등성 검증)
        """
        sh.add_search("keep me", 5)
        sh.add_search("also keep", 3)
        # 롤백 전 히스토리 스냅샷 (깊은 복사)
        snapshot_before = {k: dict(v) for k, v in sh.history.items()}

        with patch.object(sh, "_save_history", return_value=False):
            result = sh.clear_all()

        assert result is False
        # 정확한 히스토리 동등성
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
        """avg_results가 소수점 첫째 자리로 반올림됩니다.
        (Comment 5: 비정수 평균값으로 반올림 회귀를 감지합니다)
        avg = (1 + 2 + 4) / 3 = 2.333... → round(2.333..., 1) = 2.3
        """
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
# _save_history 원자적 쓰기 테스트
# ─────────────────────────────────────────────────────────


class TestSaveHistory:
    """_save_history의 원자적 쓰기 및 파일 I/O 오류 경로를 검증합니다."""

    def test_save_history_does_not_corrupt_existing_file_on_write_failure(
        self, sh: SearchHistory
    ):
        """쓰기 오류 발생 시 기존 파일이 손상되지 않습니다.
        (Comment 1: 원자적 쓰기 — 임시 파일 접근 실패 시 기존 파일 보존 검증)
        """
        # 먼저 정상적인 초기 데이터 저장
        sid = sh.add_search("original", 5)
        assert os.path.exists(sh.storage_path)
        with open(sh.storage_path, encoding="utf-8") as f:
            original_content = f.read()
        assert "original" in original_content

        # NamedTemporaryFile 생성 단계에서 OSError를 주입하여 쓰기 실패를 시뮬레이션
        sh.history["new_key"] = {
            "query": "new",
            "results_count": 1,
            "top_results": [],
            "search_time": "2026-01-01T00:00:00",
            "created_at": "2026-01-01 00:00:00",
        }
        with patch("tempfile.NamedTemporaryFile", side_effect=OSError("disk full")):
            result = sh._save_history()

        assert result is False
        # 기존 파일이 손상되지 않고 원본 내용 유지
        with open(sh.storage_path, encoding="utf-8") as f:
            after_content = f.read()
        assert after_content == original_content

    def test_save_history_returns_false_on_write_oserror(self, sh: SearchHistory):
        """NamedTemporaryFile 생성 실패 시 False를 반환합니다."""
        sh.history = {
            "k": {
                "query": "q",
                "results_count": 1,
                "top_results": [],
                "search_time": "2026-01-01T00:00:00",
                "created_at": "2026-01-01 00:00:00",
            }
        }
        with patch("tempfile.NamedTemporaryFile", side_effect=OSError("disk full")):
            result = sh._save_history()
        assert result is False

    def test_save_history_returns_true_on_success(self, sh: SearchHistory):
        """정상적인 저장은 True를 반환하고 파일이 존재합니다."""
        sh.add_search("saved", 3)
        assert os.path.exists(sh.storage_path)


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

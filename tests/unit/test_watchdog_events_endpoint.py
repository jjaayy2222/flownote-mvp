# tests/unit/test_watchdog_events_endpoint.py

"""
Unit tests for Watchdog Events API endpoint (#12.3.32).

Covers:
- GET /automation/watchdog/events:
  - 파일 미존재 시 빈 목록 반환 (200 OK, total=0, events=[])
  - 정상 JSONL 로그 읽기 및 필드 정합성 검증 (200 OK)
  - timestamp 역순(최신순) 정렬 검증 (naive/aware 혼합 정렬 안전성 포함)
  - event_type 필터링 검증 (대소문자 무관)
  - limit 페이징 슬라이싱 동작 검증 (total vs len(events))
  - 손상된 라인(비-dict, JSON 파싱 오류, 필수 필드 누락, 유효하지 않은 event_type) 자동 스킵 복원력 검증
  - action 및 status 누락 시 안전한 기본값 부여 검증
  - OSError 발생 시 500 Internal Server Error 처리 검증
  - backend.main:app 내 라우터 등록 및 엔드포인트 접근성 검증
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.endpoints.automation import (
    WatchdogEventListResponse,
    get_watchdog_events,
)
from backend.config import PathConfig
from backend.main import app


@pytest.fixture
def temp_watchdog_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """임시 PathConfig.DATA_DIR를 제공하고 watchdog 디렉터리 경로를 설정하는 픽스처."""
    monkeypatch.setattr(PathConfig, "DATA_DIR", tmp_path)
    watchdog_dir = tmp_path / "watchdog"
    watchdog_dir.mkdir(parents=True, exist_ok=True)
    events_file = watchdog_dir / "events.jsonl"
    return {"dir": watchdog_dir, "file": events_file, "root": tmp_path}


@pytest.mark.asyncio
async def test_get_watchdog_events_nonexistent_file(temp_watchdog_env):
    """이벤트 로그 파일이 없을 때 빈 응답을 200 OK로 반환하는지 검증."""
    events_file = temp_watchdog_env["file"]
    if events_file.exists():
        events_file.unlink()

    response = await get_watchdog_events(limit=50, event_type=None)
    assert isinstance(response, WatchdogEventListResponse)
    assert response.total == 0
    assert response.events == []


@pytest.mark.asyncio
async def test_get_watchdog_events_success(temp_watchdog_env):
    """정상적인 JSONL 레코드가 주어졌을 때 데이터가 올바르게 반환되는지 검증."""
    events_file = temp_watchdog_env["file"]
    records = [
        {
            "event_id": "evt_001",
            "timestamp": "2026-10-18T10:00:00+09:00",
            "event_type": "created",
            "file_path": "Projects/Idea.md",
            "action": "Triggered Reclassification",
            "status": "completed",
        },
        {
            "event_id": "evt_002",
            "timestamp": "2026-10-18T11:00:00+09:00",
            "event_type": "modified",
            "file_path": "Areas/Health.md",
            "action": "Updated Embedding",
            "status": "completed",
        },
    ]
    with open(events_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    response = await get_watchdog_events(limit=50, event_type=None)
    assert response.total == 2
    assert len(response.events) == 2

    # 최신순(evt_002 -> 11:00, evt_001 -> 10:00) 정렬 확인
    assert response.events[0].event_id == "evt_002"
    assert response.events[0].event_type == "modified"
    assert response.events[0].file_path == "Areas/Health.md"
    assert response.events[0].status == "completed"

    assert response.events[1].event_id == "evt_001"
    assert response.events[1].event_type == "created"


@pytest.mark.asyncio
async def test_get_watchdog_events_sorting_mixed_timezones(temp_watchdog_env):
    """UTC, 타임존 명시, naive datetime이 혼합되어 있어도 타입 에러 없이 최신순 정렬되는지 검증."""
    events_file = temp_watchdog_env["file"]
    records = [
        {
            "event_id": "evt_old",
            "timestamp": "2026-10-18T01:00:00Z",  # UTC 01:00
            "event_type": "created",
            "file_path": "old.md",
        },
        {
            "event_id": "evt_latest",
            "timestamp": "2026-10-18T12:00:00+00:00",  # UTC 12:00
            "event_type": "modified",
            "file_path": "latest.md",
        },
        {
            "event_id": "evt_naive",
            "timestamp": "2026-10-18T05:00:00",  # naive -> UTC 05:00 간주
            "event_type": "deleted",
            "file_path": "naive.md",
        },
    ]
    with open(events_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    response = await get_watchdog_events(limit=50, event_type=None)
    assert response.total == 3
    event_ids = [e.event_id for e in response.events]
    assert event_ids == ["evt_latest", "evt_naive", "evt_old"]


@pytest.mark.asyncio
async def test_get_watchdog_events_filter_by_type(temp_watchdog_env):
    """event_type 필터링(대소문자 무관) 및 total 일관성 검증."""
    events_file = temp_watchdog_env["file"]
    records = [
        {
            "event_id": "e1",
            "timestamp": "2026-10-18T10:00:00",
            "event_type": "created",
            "file_path": "f1.md",
        },
        {
            "event_id": "e2",
            "timestamp": "2026-10-18T10:01:00",
            "event_type": "modified",
            "file_path": "f2.md",
        },
        {
            "event_id": "e3",
            "timestamp": "2026-10-18T10:02:00",
            "event_type": "created",
            "file_path": "f3.md",
        },
        {
            "event_id": "e4",
            "timestamp": "2026-10-18T10:03:00",
            "event_type": "deleted",
            "file_path": "f4.md",
        },
    ]
    with open(events_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    # 대문자 필터 테스트
    res_created = await get_watchdog_events(limit=50, event_type="CREATED")
    assert res_created.total == 2
    assert all(e.event_type == "created" for e in res_created.events)

    # 존재하지 않는 유형 필터 테스트
    res_none = await get_watchdog_events(limit=50, event_type="unknown_type")
    assert res_none.total == 0
    assert res_none.events == []


@pytest.mark.asyncio
async def test_get_watchdog_events_limit_pagination(temp_watchdog_env):
    """limit 파라미터 적용 시 total은 전체 수, events는 limit 개수만큼 반환되는지 검증."""
    events_file = temp_watchdog_env["file"]
    with open(events_file, "w", encoding="utf-8") as f:
        for i in range(10):
            record = {
                "event_id": f"evt_{i}",
                "timestamp": f"2026-10-18T10:{i:02d}:00",
                "event_type": "modified",
                "file_path": f"file_{i}.md",
            }
            f.write(json.dumps(record) + "\n")

    response = await get_watchdog_events(limit=3, event_type=None)
    assert response.total == 10
    assert len(response.events) == 3
    # 가장 최신인 evt_9, evt_8, evt_7 순서 검증
    assert response.events[0].event_id == "evt_9"
    assert response.events[1].event_id == "evt_8"
    assert response.events[2].event_id == "evt_7"


@pytest.mark.asyncio
async def test_get_watchdog_events_skips_malformed_lines(temp_watchdog_env):
    """손상된 라인을 자동으로 스킵하고 집계 경고를 기록하는지 검증."""
    events_file = temp_watchdog_env["file"]
    with open(events_file, "w", encoding="utf-8") as f:
        f.write("\n")  # 빈 줄 (무시됨)
        f.write("not a json string\n")  # JSON 파싱 실패
        f.write(json.dumps(["not", "a", "dict"]) + "\n")  # dict 아님
        f.write(
            json.dumps({"event_id": "e_no_ts", "event_type": "created"}) + "\n"
        )  # timestamp 없음
        f.write(
            json.dumps(
                {
                    "event_id": "e_bad_ts",
                    "timestamp": "invalid_date",
                    "event_type": "created",
                }
            )
            + "\n"
        )  # 잘못된 날짜
        f.write(
            json.dumps(
                {
                    "event_id": "e_bad_type",
                    "timestamp": "2026-10-18T10:00:00",
                    "event_type": "invalid_type",
                }
            )
            + "\n"
        )  # 유효하지 않은 event_type
        # 정상 레코드 1건
        f.write(
            json.dumps(
                {
                    "event_id": "evt_valid",
                    "timestamp": "2026-10-18T10:05:00",
                    "event_type": "moved",
                    "file_path": "valid.md",
                }
            )
            + "\n"
        )

    response = await get_watchdog_events(limit=50, event_type=None)
    assert response.total == 1
    assert len(response.events) == 1
    assert response.events[0].event_id == "evt_valid"
    assert response.events[0].event_type == "moved"


@pytest.mark.asyncio
async def test_get_watchdog_events_default_fallbacks(temp_watchdog_env):
    """action 및 status 누락 시 안전한 기본값이 부여되는지 검증."""
    events_file = temp_watchdog_env["file"]
    records = [
        {"timestamp": "2026-10-18T10:00:00", "event_type": "created", "path": "p1.md"},
        {
            "timestamp": "2026-10-18T10:01:00",
            "event_type": "modified",
            "file_path": "p2.md",
            "status": "unknown_status",
        },
        {
            "timestamp": "2026-10-18T10:02:00",
            "event_type": "deleted",
            "src_path": "p3.md",
        },
    ]
    with open(events_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    response = await get_watchdog_events(limit=50, event_type=None)
    assert response.total == 3

    # deleted -> "Removed Index" 기본 action
    e_del = next(e for e in response.events if e.event_type == "deleted")
    assert e_del.action == "Removed Index"
    assert e_del.status == "completed"
    assert e_del.file_path == "p3.md"

    # modified with unknown_status -> fallback status "completed"
    e_mod = next(e for e in response.events if e.event_type == "modified")
    assert e_mod.action == "Updated Embedding"
    assert e_mod.status == "completed"

    # created -> "Triggered Reclassification"
    e_cre = next(e for e in response.events if e.event_type == "created")
    assert e_cre.action == "Triggered Reclassification"


@pytest.mark.asyncio
async def test_get_watchdog_events_oserror_handled(temp_watchdog_env):
    """파일 I/O OSError 발생 시 500 에러로 변환되는지 검증."""
    events_file = temp_watchdog_env["file"]
    events_file.write_text("dummy", encoding="utf-8")

    with patch(
        "backend.api.endpoints.automation._read_watchdog_events",
        side_effect=OSError("Disk read failure"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_watchdog_events(limit=50, event_type=None)
        assert exc_info.value.status_code == 500
        assert (
            "Watchdog 이벤트 로그를 읽는 중 오류가 발생했습니다."
            in exc_info.value.detail
        )


def test_watchdog_events_router_registered_in_main_app(temp_watchdog_env):
    """backend.main:app에서 /api/automation/watchdog/events 엔드포인트 접근이 정상적인지 검증."""
    client = TestClient(app)
    response = client.get("/api/automation/watchdog/events")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "events" in data
    assert isinstance(data["events"], list)

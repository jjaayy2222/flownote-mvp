# tests/unit/test_get_conflicts_endpoint.py

"""
Unit tests for GET /api/sync/conflicts endpoint.
Covers the real JSONL-backed implementation introduced in #12.3.28:
- JSONL 파일 읽기 및 ConflictLogResponse 필드 매핑
- 최신순 정렬 (detected_at 기준 내림차순)
- status 필터링 ("pending", "resolved" 등)
- limit 매개변수 적용
- 파일 미존재 및 빈 파일 안전 처리
- 손상된 JSON 줄 및 비정상 타임스탬프 오류 복원력
- 읽기 실패(OSError) 시 500 에러 반환
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api.endpoints.sync import get_conflicts
from backend.config import PathConfig
from backend.models.external_sync import (
    ConnectionConfig,
    ExternalToolConnection,
    ExternalToolType,
)
from backend.services.sync_service import SyncServiceBase


class DummySyncService(SyncServiceBase):
    """SyncServiceBase 단위 테스트를 위한 최소 구체 클래스."""

    async def connect(self) -> bool:
        return True

    async def sync_all(self):
        return []

    async def pull_file(self, external_id: str):
        return None

    async def push_file(self, internal_id: str, content: str) -> bool:
        return True


@pytest.fixture
def mock_conflict_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """PathConfig.DATA_DIR를 임시 디렉터리로 교체하고 sync_logs 경로를 반환하는 픽스처."""
    monkeypatch.setattr(PathConfig, "DATA_DIR", tmp_path)
    log_dir = tmp_path / "sync_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@pytest.mark.asyncio
async def test_get_conflicts_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """로그 파일이 존재하지 않는 경우 빈 리스트 반환 검증."""
    monkeypatch.setattr(PathConfig, "DATA_DIR", tmp_path)
    # sync_logs 디렉터리 및 파일이 없는 상태
    results = await get_conflicts()
    assert results == []


@pytest.mark.asyncio
async def test_get_conflicts_empty_file(mock_conflict_log_dir: Path):
    """로그 파일이 비어있는 경우 빈 리스트 반환 검증."""
    log_file = mock_conflict_log_dir / "detected_conflicts.jsonl"
    log_file.write_text("", encoding="utf-8")

    results = await get_conflicts()
    assert results == []


@pytest.mark.asyncio
async def test_get_conflicts_field_mapping(mock_conflict_log_dir: Path):
    """JSONL 레코드의 필드가 ConflictLogResponse 모델에 정상 매핑되는지 검증."""
    log_file = mock_conflict_log_dir / "detected_conflicts.jsonl"
    sample_record = {
        "conflict_id": "conflict-001",
        "file_id": "file-123",
        "external_path": "notes/project_a.md",
        "tool_type": "obsidian",
        "conflict_type": "content_diverged",
        "local_hash": "hash_local_abc",
        "remote_hash": "hash_remote_def",
        "detected_at": "2026-10-12T09:00:00",
    }
    log_file.write_text(
        json.dumps(sample_record, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    results = await get_conflicts()

    assert len(results) == 1
    item = results[0]
    assert item.conflict_id == "conflict-001"
    assert item.file_path == "notes/project_a.md"
    assert item.conflict_type == "content_diverged"
    assert item.local_hash == "hash_local_abc"
    assert item.remote_hash == "hash_remote_def"
    assert item.status == "pending"  # JSONL에 status 부재 시 기본값
    assert item.timestamp == datetime.fromisoformat("2026-10-12T09:00:00")
    assert item.resolution_method is None
    assert item.notes is None


@pytest.mark.asyncio
async def test_get_conflicts_sorting_descending(mock_conflict_log_dir: Path):
    """충돌 이력이 최신 발생 순(detected_at 내림차순)으로 정렬되는지 검증."""
    log_file = mock_conflict_log_dir / "detected_conflicts.jsonl"
    records = [
        {
            "conflict_id": "c-early",
            "external_path": "a.md",
            "detected_at": "2026-10-10T10:00:00",
        },
        {
            "conflict_id": "c-latest",
            "external_path": "b.md",
            "detected_at": "2026-10-12T12:00:00",
        },
        {
            "conflict_id": "c-mid",
            "external_path": "c.md",
            "detected_at": "2026-10-11T11:00:00",
        },
    ]
    lines = "\n".join(json.dumps(r) for r in records) + "\n"
    log_file.write_text(lines, encoding="utf-8")

    results = await get_conflicts()

    assert len(results) == 3
    assert [r.conflict_id for r in results] == ["c-latest", "c-mid", "c-early"]


@pytest.mark.asyncio
async def test_get_conflicts_status_filter(mock_conflict_log_dir: Path):
    """status 쿼리 파라미터 필터링 동작 검증."""
    log_file = mock_conflict_log_dir / "detected_conflicts.jsonl"
    records = [
        {
            "conflict_id": "c-pending-1",
            "detected_at": "2026-10-12T10:00:00",
            # status 미기재 -> "pending" 처리
        },
        {
            "conflict_id": "c-resolved-1",
            "detected_at": "2026-10-12T11:00:00",
            "status": "resolved",
            "resolution_method": "use_remote",
        },
        {
            "conflict_id": "c-pending-2",
            "detected_at": "2026-10-12T12:00:00",
            "status": "pending",
        },
    ]
    lines = "\n".join(json.dumps(r) for r in records) + "\n"
    log_file.write_text(lines, encoding="utf-8")

    # pending 필터
    pending_results = await get_conflicts(status="pending")
    assert len(pending_results) == 2
    assert {r.conflict_id for r in pending_results} == {"c-pending-1", "c-pending-2"}

    # resolved 필터
    resolved_results = await get_conflicts(status="resolved")
    assert len(resolved_results) == 1
    assert resolved_results[0].conflict_id == "c-resolved-1"
    assert resolved_results[0].resolution_method == "use_remote"


@pytest.mark.asyncio
async def test_get_conflicts_limit(mock_conflict_log_dir: Path):
    """limit 매개변수 적용 검증."""
    log_file = mock_conflict_log_dir / "detected_conflicts.jsonl"
    records = [
        {"conflict_id": f"c-{i}", "detected_at": f"2026-10-{10+i:02d}T10:00:00"}
        for i in range(5)
    ]
    lines = "\n".join(json.dumps(r) for r in records) + "\n"
    log_file.write_text(lines, encoding="utf-8")

    results = await get_conflicts(limit=2)
    assert len(results) == 2
    # 최신 2건 (c-4, c-3)
    assert [r.conflict_id for r in results] == ["c-4", "c-3"]


@pytest.mark.asyncio
async def test_get_conflicts_parse_error_tolerance(mock_conflict_log_dir: Path):
    """손상된 줄이나 비정상 JSON 줄이 있어도 건너뛰고 정상 레코드를 반환하는지 검증."""
    log_file = mock_conflict_log_dir / "detected_conflicts.jsonl"
    content = (
        '{"conflict_id": "valid-1", "detected_at": "2026-10-12T10:00:00"}\n'
        "invalid json format line {{{}}\n"
        '"just a string, not a dict"\n'
        "\n"  # 빈 줄
        '{"conflict_id": "valid-2", "detected_at": "2026-10-12T11:00:00"}\n'
    )
    log_file.write_text(content, encoding="utf-8")

    results = await get_conflicts()
    assert len(results) == 2
    assert [r.conflict_id for r in results] == ["valid-2", "valid-1"]


@pytest.mark.asyncio
async def test_get_conflicts_invalid_timestamp_fallback(mock_conflict_log_dir: Path):
    """detected_at이 올바르지 않은 형식이거나 누락된 경우 기본 timestamp가 할당되는지 검증."""
    log_file = mock_conflict_log_dir / "detected_conflicts.jsonl"
    record = {
        "conflict_id": "c-invalid-time",
        "detected_at": "not-a-valid-iso-date",
    }
    log_file.write_text(json.dumps(record) + "\n", encoding="utf-8")

    results = await get_conflicts()
    assert len(results) == 1
    assert results[0].conflict_id == "c-invalid-time"
    assert isinstance(results[0].timestamp, datetime)


@pytest.mark.asyncio
async def test_get_conflicts_oserror_raises_500(mock_conflict_log_dir: Path):
    """로그 파일 읽기 중 OSError 발생 시 500 HTTPException 반환 검증."""
    log_file = mock_conflict_log_dir / "detected_conflicts.jsonl"
    log_file.write_text('{"conflict_id": "test"}\n', encoding="utf-8")

    with patch("builtins.open", side_effect=OSError("Disk read error")):
        with pytest.raises(HTTPException) as exc_info:
            await get_conflicts()

        assert exc_info.value.status_code == 500
        assert "서버 내부 오류" in exc_info.value.detail


@pytest.mark.asyncio
async def test_detect_conflict_3way_persists_record_and_get_conflicts(
    mock_conflict_log_dir: Path,
):
    """
    3-way 충돌 감지 시 _handle_conflict가 자동 호출되어 JSONL 파일에 기록되고,
    이를 get_conflicts() 엔드포인트에서 정상적으로 조회할 수 있는지 검증.
    """
    conn = ExternalToolConnection(
        tool_type=ExternalToolType.OBSIDIAN,
        config=ConnectionConfig(base_path="/tmp/mock_vault", enabled=True),
    )
    service = DummySyncService(conn)

    # 1. 충돌 없는 경우 (로컬만 변경) -> JSONL에 기록되지 않아야 함
    no_conflict = service.detect_conflict_3way(
        file_id="/path/to/note.md",
        external_path="vault/note.md",
        local_hash="local_changed_123",
        remote_hash="synced_hash_000",
        last_synced_hash="synced_hash_000",
    )
    assert no_conflict is None
    log_file = mock_conflict_log_dir / "detected_conflicts.jsonl"
    assert not log_file.exists() or log_file.read_text().strip() == ""

    # 2. 충돌 발생 (양쪽 모두 변경) -> SyncConflict 반환 및 JSONL 파일 기록
    conflict = service.detect_conflict_3way(
        file_id="/path/to/note.md",
        external_path="vault/note.md",
        local_hash="local_new_abc1234567890",
        remote_hash="remote_new_def9876543210",
        last_synced_hash="synced_hash_000",
    )
    assert conflict is not None
    assert log_file.exists()

    # JSONL 파일 내용 확인 (PII 마스킹 및 해시 길이 검증)
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    raw_data = json.loads(lines[0])
    assert raw_data["conflict_id"] == conflict.conflict_id
    assert raw_data["external_path"] == "vault/note.md"
    assert raw_data["local_hash"] == "local_new_abc123"  # 16자리 절삭
    assert raw_data["remote_hash"] == "remote_new_def9"  # 16자리 절삭
    assert raw_data["status"] == "pending"
    assert "note.md_" in raw_data["file_id"]  # PII 마스킹 (get_safe_file_id)

    # 3. get_conflicts() 엔드포인트를 통해 조회가 되는지 확인
    results = await get_conflicts()
    assert len(results) == 1
    assert results[0].conflict_id == conflict.conflict_id
    assert results[0].file_path == "vault/note.md"
    assert results[0].status == "pending"


def test_detect_conflict_3way_handles_oserror_gracefully(
    mock_conflict_log_dir: Path,
):
    """
    _handle_conflict()에서 파일 쓰기 중 OSError가 발생하더라도
    충돌 감지(detect_conflict_3way) 프로세스가 중단되지 않고 SyncConflict를 정상 반환하는지 검증.
    """
    conn = ExternalToolConnection(
        tool_type=ExternalToolType.OBSIDIAN,
        config=ConnectionConfig(base_path="/tmp/mock_vault", enabled=True),
    )
    service = DummySyncService(conn)

    with patch("builtins.open", side_effect=OSError("Disk full")):
        conflict = service.detect_conflict_3way(
            file_id="/path/to/note.md",
            external_path="vault/note.md",
            local_hash="local_1",
            remote_hash="remote_2",
            last_synced_hash="base_0",
        )
        assert conflict is not None
        assert conflict.external_path == "vault/note.md"

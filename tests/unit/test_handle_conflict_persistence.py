"""Tests for persistent, privacy-conscious sync conflict records."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config import PathConfig
from backend.models.conflict import ResolutionStatus, SyncConflict, SyncConflictType
from backend.models.external_sync import (
    ConnectionConfig,
    ExternalToolConnection,
    ExternalToolType,
)
from backend.services.sync_service import SyncServiceBase


class DummySyncService(SyncServiceBase):
    async def connect(self) -> bool:
        return True

    async def sync_all(self) -> list[SyncConflict]:
        return []

    async def pull_file(self, external_id: str) -> str | None:
        return None

    async def push_file(self, internal_id: str, content: str) -> bool:
        return True


@pytest.fixture
def service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DummySyncService:
    monkeypatch.setattr(PathConfig, "DATA_DIR", tmp_path)
    connection = ExternalToolConnection(
        tool_type=ExternalToolType.OBSIDIAN,
        config=ConnectionConfig(vault_path=str(tmp_path / "vault")),
    )
    return DummySyncService(connection)


@pytest.fixture
def conflict() -> SyncConflict:
    return SyncConflict(
        file_id="/private/user/notes/secret.md",
        external_path="/Vault/Notes/note.md",
        tool_type=ExternalToolType.OBSIDIAN,
        conflict_type=SyncConflictType.CONTENT_MISMATCH,
        local_hash="a" * 64,
        remote_hash="b" * 64,
    )


def read_records(tmp_path: Path) -> list[dict[str, object]]:
    path = tmp_path / "sync_logs" / "detected_conflicts.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_handle_conflict_persists_append_only_privacy_safe_record(
    service: DummySyncService, conflict: SyncConflict, tmp_path: Path
) -> None:
    assert service._handle_conflict(conflict) is False
    second = conflict.model_copy(update={"external_path": "/Vault/Notes/second.md"})
    assert service._handle_conflict(second) is False

    records = read_records(tmp_path)
    assert len(records) == 2
    assert records[0]["conflict_id"] == conflict.conflict_id
    assert records[0]["file_id"] != conflict.file_id
    assert records[0]["external_path"] == conflict.external_path
    assert records[0]["local_hash"] == "a" * 16
    assert records[0]["remote_hash"] == "b" * 16
    assert records[0]["status"] == ResolutionStatus.PENDING.value
    assert records[0]["tool_type"] == ExternalToolType.OBSIDIAN.value
    assert records[0]["conflict_type"] == SyncConflictType.CONTENT_MISMATCH.value


def test_sync_conflict_default_timestamp_is_utc_aware(conflict: SyncConflict) -> None:
    assert conflict.detected_at.tzinfo is not None
    assert conflict.detected_at.utcoffset().total_seconds() == 0


def test_handle_conflict_normalizes_legacy_naive_timestamp(
    service: DummySyncService, conflict: SyncConflict, tmp_path: Path
) -> None:
    naive = datetime(2026, 10, 23, 12, 30)
    conflict = conflict.model_copy(update={"detected_at": naive})

    service._handle_conflict(conflict)

    detected_at = datetime.fromisoformat(str(read_records(tmp_path)[0]["detected_at"]))
    assert detected_at.tzinfo == timezone.utc


def test_handle_conflict_uses_utc_when_timestamp_is_missing(
    service: DummySyncService, conflict: SyncConflict, tmp_path: Path
) -> None:
    conflict = conflict.model_copy(update={"detected_at": None})
    service._handle_conflict(conflict)

    detected_at = datetime.fromisoformat(str(read_records(tmp_path)[0]["detected_at"]))
    assert detected_at.tzinfo == timezone.utc


def test_handle_conflict_contains_oserror(
    service: DummySyncService, conflict: SyncConflict
) -> None:
    with patch("builtins.open", side_effect=OSError("disk full")):
        assert service._handle_conflict(conflict) is False

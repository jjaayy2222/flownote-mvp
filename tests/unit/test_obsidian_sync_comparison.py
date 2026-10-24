"""Tests for mapped Obsidian file comparison and synchronization."""

import hashlib
import json
from pathlib import Path

import pytest

from backend.config import PathConfig
from backend.config.mcp_config import ObsidianConfig
from backend.mcp import obsidian_server
from backend.mcp.sync_map_manager import SyncMapManager
from backend.models.external_sync import ExternalToolType


@pytest.fixture
def setup_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[obsidian_server.ObsidianSyncService, SyncMapManager, Path, Path]:
    monkeypatch.setattr(PathConfig, "DATA_DIR", tmp_path / "data")
    vault = tmp_path / "vault"
    vault.mkdir()
    local_file = tmp_path / "local.md"
    remote_file = vault / "note.md"
    local_file.write_text("baseline", encoding="utf-8")
    remote_file.write_text("baseline", encoding="utf-8")

    manager = SyncMapManager(storage_dir=str(tmp_path / "mappings"))
    manager.update_mapping(
        internal_id=str(local_file),
        external_path=str(remote_file),
        tool_type=ExternalToolType.OBSIDIAN,
        current_hash=hashlib.sha256(b"baseline").hexdigest(),
    )
    monkeypatch.setattr(obsidian_server, "get_sync_map_manager", lambda: manager)
    service = obsidian_server.ObsidianSyncService(ObsidianConfig(vault_path=str(vault)))
    return service, manager, local_file, remote_file


@pytest.mark.asyncio
async def test_sync_all_pushes_local_only_change_and_advances_mapping(setup_sync):
    service, manager, local_file, remote_file = setup_sync
    local_file.write_text("local update", encoding="utf-8")

    assert await service.sync_all() == []

    assert remote_file.read_text(encoding="utf-8") == "local update"
    mapping = manager.get_mapping_by_internal_id(str(local_file))
    assert mapping is not None
    assert mapping.last_synced_hash == service.calculate_file_hash("local update")


@pytest.mark.asyncio
async def test_sync_all_pulls_remote_only_change(setup_sync):
    service, manager, local_file, remote_file = setup_sync
    remote_file.write_text("remote update", encoding="utf-8")

    assert await service.sync_all() == []

    assert local_file.read_text(encoding="utf-8") == "remote update"
    mapping = manager.get_mapping_by_internal_id(str(local_file))
    assert mapping is not None
    assert mapping.last_synced_hash == service.calculate_file_hash("remote update")


@pytest.mark.asyncio
async def test_sync_all_persists_conflict_when_both_sides_change(setup_sync):
    service, _, local_file, remote_file = setup_sync
    local_file.write_text("local update", encoding="utf-8")
    remote_file.write_text("remote update", encoding="utf-8")

    conflicts = await service.sync_all()

    assert len(conflicts) == 1
    assert conflicts[0].file_id == str(local_file)
    assert local_file.read_text(encoding="utf-8") == "local update"
    assert remote_file.read_text(encoding="utf-8") == "remote update"
    records = [
        json.loads(line)
        for line in (PathConfig.DATA_DIR / "sync_logs" / "detected_conflicts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert records[0]["conflict_id"] == conflicts[0].conflict_id


@pytest.mark.asyncio
async def test_sync_all_ignores_unmapped_markdown(setup_sync):
    service, _, _, remote_file = setup_sync
    (remote_file.parent / "unmapped.md").write_text("untracked", encoding="utf-8")

    assert await service.sync_all() == []

"""Tests for MCP status reporting when stdio runtime telemetry is unavailable."""

import json

import pytest

from backend.api.endpoints.sync import get_mcp_status
from backend.config import RedisConfig
from backend.mcp import runtime_status
from backend.mcp.runtime_status import _status_key_prefix, read_mcp_runtime_status


def test_mcp_status_key_prefix_is_scoped_to_installation(monkeypatch):
    monkeypatch.setattr(RedisConfig, "MCP_RUNTIME_NAMESPACE", "installation-a")
    first_prefix = _status_key_prefix()
    monkeypatch.setattr(RedisConfig, "MCP_RUNTIME_NAMESPACE", "installation-b")

    assert first_prefix == "flownote:mcp:installation-a:stdio:runtime:"
    assert _status_key_prefix() == "flownote:mcp:installation-b:stdio:runtime:"


def test_invalid_or_missing_mcp_namespace_disables_status_keys(monkeypatch):
    for namespace in ("", "../shared", "wild*card"):
        monkeypatch.setattr(RedisConfig, "MCP_RUNTIME_NAMESPACE", namespace)
        assert _status_key_prefix() is None


@pytest.mark.asyncio
async def test_runtime_reader_scans_only_the_configured_installation(monkeypatch):
    monkeypatch.setattr(RedisConfig, "MCP_RUNTIME_NAMESPACE", "installation-a")

    class FakeRedis:
        pattern = None

        async def ping(self):
            return True

        async def scan_iter(self, match):
            self.pattern = match
            yield "flownote:mcp:installation-a:stdio:runtime:session"

        async def get(self, key):
            return json.dumps(
                {
                    "session_id": "opaque-session",
                    "transport": "stdio",
                    "tools": ["search_notes"],
                    "resources": ["flownote://dashboard/summary"],
                }
            )

        async def aclose(self):
            return None

    fake_redis = FakeRedis()
    monkeypatch.setattr(
        runtime_status.redis, "from_url", lambda *args, **kwargs: fake_redis
    )

    result = await read_mcp_runtime_status()

    assert fake_redis.pattern == "flownote:mcp:installation-a:stdio:runtime:*"
    assert result is not None
    assert result["running"] is True
    assert result["active_sessions"] == 1
    assert result["tools_registered"] == ["search_notes"]
    assert result["resources_registered"] == ["flownote://dashboard/summary"]


@pytest.mark.asyncio
async def test_get_mcp_status_does_not_report_api_registry_as_stdio_state(monkeypatch):
    """Separate stdio runtime state must stay unknown without shared telemetry."""
    monkeypatch.setattr(RedisConfig, "MCP_RUNTIME_NAMESPACE", "")
    result = await get_mcp_status()

    assert result.running is None
    assert result.active_clients is None
    assert result.tools_registered is None
    assert result.resources_registered is None
    assert result.active_sessions is None

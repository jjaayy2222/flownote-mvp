"""Tests for MCP status reporting when stdio runtime telemetry is unavailable."""

import pytest

from backend.api.endpoints.sync import get_mcp_status


@pytest.mark.asyncio
async def test_get_mcp_status_does_not_report_api_registry_as_stdio_state():
    """Separate stdio runtime state must stay unknown without shared telemetry."""
    result = await get_mcp_status()

    assert result.running is None
    assert result.active_clients is None
    assert result.tools_registered is None
    assert result.resources_registered is None

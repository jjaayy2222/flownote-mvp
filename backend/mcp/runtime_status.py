"""Redis-backed status channel shared by the MCP stdio and API processes."""

import json
import logging
import uuid
from contextlib import suppress
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from redis.exceptions import RedisError

from backend.config import RedisConfig

logger = logging.getLogger(__name__)

_STATUS_KEY_PREFIX = "flownote:mcp:stdio:runtime:"
_STATUS_TTL_SECONDS = 30


def _collect_registered_names(
    sessions: Dict[str, Dict[str, Any]], field: str
) -> List[str]:
    names = {
        name
        for session in sessions.values()
        for name in (
            session.get(field, []) if isinstance(session.get(field), list) else []
        )
        if isinstance(name, str)
    }
    return sorted(names)


class MCPRuntimeStatusPublisher:
    """Publish one stdio process/session heartbeat without client PII."""

    def __init__(self) -> None:
        self.session_id = uuid.uuid4().hex
        self._key = f"{_STATUS_KEY_PREFIX}{self.session_id}"
        self._client: Optional[redis.Redis] = None

    async def publish(self, tools: List[str], resources: List[str]) -> bool:
        """Write a short-lived runtime snapshot. Redis failure is non-fatal."""
        try:
            if self._client is None:
                self._client = redis.from_url(
                    RedisConfig.REDIS_URL, decode_responses=True
                )
            payload = json.dumps(
                {
                    "session_id": self.session_id,
                    "transport": "stdio",
                    "tools": tools,
                    "resources": resources,
                },
                separators=(",", ":"),
            )
            await self._client.set(self._key, payload, ex=_STATUS_TTL_SECONDS)
            return True
        except (RedisError, OSError, ValueError):
            logger.warning("MCP runtime status publish failed.")
            return False

    async def close(self) -> None:
        """Remove the process snapshot and close its dedicated Redis connection."""
        if self._client is None:
            return
        try:
            await self._client.delete(self._key)
        except (RedisError, OSError, ValueError):
            logger.warning("MCP runtime status cleanup failed.")
        finally:
            with suppress(RedisError, OSError, ValueError):
                await self._client.aclose()
            self._client = None


async def read_mcp_runtime_status() -> Optional[Dict[str, Any]]:
    """Aggregate active stdio process snapshots; None means telemetry unavailable."""
    client: Optional[redis.Redis] = None
    try:
        client = redis.from_url(RedisConfig.REDIS_URL, decode_responses=True)
        if not await client.ping():
            return None

        payloads: List[str] = []
        async for key in client.scan_iter(match=f"{_STATUS_KEY_PREFIX}*"):
            value = await client.get(key)
            if value is not None:
                payloads.append(value)

        sessions: Dict[str, Dict[str, Any]] = {}
        for payload in payloads:
            try:
                data = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                continue
            if (
                isinstance(data, dict)
                and isinstance(data.get("session_id"), str)
                and data.get("transport") == "stdio"
            ):
                sessions[data["session_id"]] = data

        tools = _collect_registered_names(sessions, "tools")
        resources = _collect_registered_names(sessions, "resources")
        return {
            "running": bool(sessions),
            # Report transport type, never client names or process-scoped IDs.
            "active_clients": ["stdio" for _ in sessions],
            "active_sessions": len(sessions),
            "tools_registered": tools,
            "resources_registered": resources,
        }
    except (RedisError, OSError, ValueError):
        logger.warning("MCP runtime status read failed.")
        return None
    finally:
        if client is not None:
            with suppress(RedisError, OSError, ValueError):
                await client.aclose()

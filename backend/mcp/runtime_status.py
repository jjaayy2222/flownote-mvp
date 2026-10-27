"""Redis-backed status channel shared by the MCP stdio and API processes."""

import logging
import re
import threading
import uuid
from contextlib import suppress
from typing import Dict, List, Literal, Optional

import redis.asyncio as redis
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.exceptions import RedisError

from backend.config import RedisConfig

logger = logging.getLogger(__name__)


class MCPRuntimeSnapshot(BaseModel):
    """Validated Redis snapshot published by one MCP stdio process."""

    model_config = ConfigDict(extra="ignore")

    session_id: str
    transport: Literal["stdio"]
    tools: List[str] = Field(default_factory=list)
    resources: List[str] = Field(default_factory=list)


_STATUS_TTL_SECONDS = 30
_NAMESPACE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_read_failure_lock = threading.Lock()
_read_failure_logged = False
_malformed_snapshot_logged = False


def _status_key_prefix() -> Optional[str]:
    """Return an installation-scoped key prefix, or disable telemetry safely."""
    namespace = RedisConfig.MCP_RUNTIME_NAMESPACE
    if not namespace or not _NAMESPACE_PATTERN.fullmatch(namespace):
        return None
    return f"flownote:mcp:{namespace}:stdio:runtime:"


def _collect_registered_names(
    sessions: Dict[str, MCPRuntimeSnapshot], field: Literal["tools", "resources"]
) -> List[str]:
    return sorted(
        {name for session in sessions.values() for name in getattr(session, field)}
    )


def _log_read_failure_once() -> None:
    global _read_failure_logged
    with _read_failure_lock:
        if not _read_failure_logged:
            logger.warning("MCP runtime status read failed; telemetry is unavailable.")
            _read_failure_logged = True


def _reset_read_failure_log() -> None:
    global _read_failure_logged
    with _read_failure_lock:
        _read_failure_logged = False


def _log_malformed_snapshots_once(count: int) -> None:
    global _malformed_snapshot_logged
    with _read_failure_lock:
        if count and not _malformed_snapshot_logged:
            logger.warning(
                "Malformed MCP runtime snapshots skipped.",
                extra={"malformed_count": count},
            )
            _malformed_snapshot_logged = True
        elif not count:
            _malformed_snapshot_logged = False


class MCPRuntimeStatusPublisher:
    """Publish one stdio process/session heartbeat without client PII."""

    def __init__(self) -> None:
        self.session_id = uuid.uuid4().hex
        key_prefix = _status_key_prefix()
        self._key = f"{key_prefix}{self.session_id}" if key_prefix else None
        self._client: Optional[redis.Redis] = None
        self._publish_failure_logged = False
        if self._key is None:
            logger.warning(
                "MCP runtime status telemetry is disabled; configure a valid installation namespace."
            )

    async def publish(self, tools: List[str], resources: List[str]) -> bool:
        """Write a short-lived runtime snapshot. Redis failure is non-fatal."""
        if self._key is None:
            return False
        try:
            if self._client is None:
                self._client = redis.from_url(
                    RedisConfig.REDIS_URL, decode_responses=True
                )
            payload = MCPRuntimeSnapshot(
                session_id=self.session_id,
                transport="stdio",
                tools=tools,
                resources=resources,
            )
            await self._client.set(
                self._key, payload.model_dump_json(), ex=_STATUS_TTL_SECONDS
            )
            self._publish_failure_logged = False
            return True
        except (RedisError, OSError, ValueError):
            if not self._publish_failure_logged:
                logger.warning(
                    "MCP runtime status publish failed; telemetry is unavailable."
                )
                self._publish_failure_logged = True
            return False

    async def close(self) -> None:
        """Remove the process snapshot and close its dedicated Redis connection."""
        if self._client is None or self._key is None:
            return
        try:
            await self._client.delete(self._key)
        except (RedisError, OSError, ValueError):
            logger.warning("MCP runtime status cleanup failed.")
        finally:
            with suppress(RedisError, OSError, ValueError):
                await self._client.aclose()
            self._client = None


async def read_mcp_runtime_status() -> Optional[Dict[str, object]]:
    """Aggregate active stdio process snapshots; None means telemetry unavailable."""
    key_prefix = _status_key_prefix()
    if key_prefix is None:
        return None

    client: Optional[redis.Redis] = None
    try:
        client = redis.from_url(RedisConfig.REDIS_URL, decode_responses=True)
        if not await client.ping():
            _log_read_failure_once()
            return None

        payloads: List[str] = []
        async for key in client.scan_iter(match=f"{key_prefix}*"):
            value = await client.get(key)
            if value is not None:
                payloads.append(value)

        sessions: Dict[str, MCPRuntimeSnapshot] = {}
        malformed_count = 0
        for payload in payloads:
            try:
                snapshot = MCPRuntimeSnapshot.model_validate_json(payload)
            except (ValidationError, ValueError, TypeError):
                malformed_count += 1
                continue
            sessions[snapshot.session_id] = snapshot
        _log_malformed_snapshots_once(malformed_count)

        _reset_read_failure_log()
        tools = _collect_registered_names(sessions, "tools")
        resources = _collect_registered_names(sessions, "resources")
        return {
            "running": bool(sessions),
            # Report transport type, never client names or process-scoped IDs.
            "active_clients": ["stdio"] if sessions else [],
            "active_sessions": len(sessions),
            "tools_registered": tools,
            "resources_registered": resources,
        }
    except (RedisError, OSError, ValueError):
        _log_read_failure_once()
        return None
    finally:
        if client is not None:
            with suppress(RedisError, OSError, ValueError):
                await client.aclose()

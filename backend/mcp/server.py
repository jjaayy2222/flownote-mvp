# backend/mcp/server.py

"""
FlowNote MCP Server
External AI agents can use FlowNote capabilities as Tools and access Resources.
"""

import asyncio
import json
import logging
import threading
from contextlib import suppress
from typing import Any, Dict, Optional

from mcp.server.fastmcp import Context, FastMCP

# FlowNote Internal Services
from backend.agent.error_utils import (  # type: ignore[import]
    build_meta,
    log_agent_error,
)
from backend.classifier.hybrid_classifier import HybridClassifier
from backend.dashboard.dashboard_core import MetadataAggregator
from backend.faiss_search import FAISSRetriever, get_persistent_retriever
from backend.mcp.auth_scope import authenticated_user_hash
from backend.mcp.runtime_status import MCPRuntimeStatusPublisher

# Initialize Logger
logger = logging.getLogger(__name__)

# Initialize FastMCP
mcp = FastMCP("FlowNote MCP Server")

# Global instances (lazy loaded)
_classifier: Optional[HybridClassifier] = None
_retriever: Optional[FAISSRetriever] = None
_aggregator: Optional[MetadataAggregator] = None

# Single thread-safe lock for lazy initialization
_lazy_lock = threading.Lock()


def _lazy_init(instance_ref: Dict[str, Any], factory) -> Any:
    """Helper for thread-safe lazy initialization"""
    if instance_ref["value"] is None:
        with _lazy_lock:
            if instance_ref["value"] is None:
                instance_ref["value"] = factory()
    return instance_ref["value"]


# Instance references container
_classifier_ref = {"value": None}
_retriever_ref = {"value": None}
_aggregator_ref = {"value": None}


def get_classifier() -> HybridClassifier:
    return _lazy_init(_classifier_ref, HybridClassifier)


def get_retriever() -> FAISSRetriever:
    """프로세스 재시작 후에도 저장된 FAISS 인덱스를 복원한다."""
    retriever = get_persistent_retriever(refresh=True)
    _retriever_ref["value"] = retriever
    return retriever


def get_aggregator() -> MetadataAggregator:
    return _lazy_init(_aggregator_ref, MetadataAggregator)


async def _run_blocking(fn, *args, **kwargs):
    """Helper to run blocking functions in a separate thread"""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except (RuntimeError, OSError, ValueError) as e:
        fn_name = fn.__name__ if hasattr(fn, "__name__") else "unknown_fn"
        meta = build_meta({"action": "run_blocking", "fn": fn_name})
        log_agent_error(logger, "Error in blocking call", e, meta)
        raise


# 1. Tools (기능 노출)


@mcp.tool()
async def classify_content(text: str) -> Dict[str, Any]:
    """
    Classify text into PARA categories (Projects, Areas, Resources, Archive) using Hybrid Classifier.

    Args:
        text: The text content to classify.
    """
    # Defensive programming: validate input
    if not text:
        return {
            "category": "Unclassified",
            "confidence": 0.0,
            "reasoning": "Input text is empty",
            "error": "empty_input",
        }

    try:
        classifier = get_classifier()
        # classify method is already async in HybridClassifier
        return await classifier.classify(text)
    except (RuntimeError, ValueError) as e:
        meta = build_meta({"action": "classify_content"})
        log_agent_error(logger, "Error during classification", e, meta)
        return {
            "category": "Unclassified",
            "confidence": 0.0,
            "error": "classification_failed",
        }


@mcp.tool()
async def search_notes(query: str, ctx: Context) -> Dict[str, Any]:
    """
    Search for notes using vector similarity search.

    Args:
        query: The search query.
        ctx: MCP 요청 컨텍스트. 인증 미들웨어가 제공한 사용자만 검색할 수 있습니다.
    """
    if not query:
        return {
            "results": [],
            "error": None,
            "metadata": {"reason": "empty_query"},
        }
    user_id_hash = authenticated_user_hash(ctx)
    if user_id_hash is None:
        return {
            "results": [],
            "error": "authentication_required",
            "metadata": {"reason": "authentication_required"},
        }

    try:
        # Wrap getter in lambda to catch init errors in _run_blocking if desired,
        # or simply rely on _run_blocking wrapping the call.
        # Here we get the retriever first. If it fails, it's caught by local try/except.
        retriever = get_retriever()
        result = await _run_blocking(
            retriever.search,
            query,
            k=5,
            metadata_filter={"user_id_hash": user_id_hash},
        )
        for item in result:
            metadata = item.get("metadata")
            if isinstance(metadata, dict):
                item["metadata"] = {
                    key: value
                    for key, value in metadata.items()
                    if key != "user_id_hash"
                }

        return {
            "results": result,
            "error": None,
            "metadata": {"reason": "ok"},
        }
    except (RuntimeError, ValueError, OSError) as e:
        meta = build_meta({"action": "search_notes"})
        log_agent_error(logger, "Error during search", e, meta)
        return {
            "results": [],
            "error": "search_failed",
            "metadata": {"reason": "exception"},
        }


@mcp.tool()
async def get_automation_stats() -> Dict[str, Any]:
    """
    Get recent automation statistics (files, searches, categories).
    """
    try:
        aggregator = get_aggregator()
        return await _run_blocking(aggregator.get_file_statistics)
    except (RuntimeError, OSError) as e:
        meta = build_meta({"action": "get_automation_stats"})
        log_agent_error(logger, "Error during stats retrieval", e, meta)
        return {"error": "stats_retrieval_failed"}


# 2. Resources (데이터 노출)


@mcp.resource("flownote://para/projects")
async def get_projects() -> str:
    """Get list of projects/categories breakdown as JSON string"""
    try:
        aggregator = get_aggregator()
        result = await _run_blocking(aggregator.get_para_breakdown)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except (RuntimeError, OSError) as e:
        meta = build_meta({"action": "get_projects"})
        log_agent_error(logger, "Error retrieval projects resource", e, meta)
        return json.dumps({"error": "resource_retrieval_failed"})


@mcp.resource("flownote://dashboard/summary")
async def get_dashboard_summary() -> str:
    """Get dashboard summary as JSON string"""
    try:
        aggregator = get_aggregator()
        result = await _run_blocking(aggregator.get_file_statistics)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except (RuntimeError, OSError) as e:
        meta = build_meta({"action": "get_dashboard_summary"})
        log_agent_error(logger, "Error retrieval dashboard summary resource", e, meta)
        return json.dumps({"error": "resource_retrieval_failed"})


if __name__ == "__main__":
    # Basic logging config for standalone execution
    logging.basicConfig(level=logging.INFO)

    async def _run_stdio_with_status() -> None:
        publisher = MCPRuntimeStatusPublisher()
        tools = [tool.name for tool in await mcp.list_tools()]
        resources = [str(resource.uri) for resource in await mcp.list_resources()]
        await publisher.publish(tools, resources)
        heartbeat = asyncio.create_task(
            _publish_runtime_heartbeat(publisher, tools, resources)
        )
        try:
            await mcp.run_stdio_async()
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            await publisher.close()

    async def _publish_runtime_heartbeat(
        publisher: MCPRuntimeStatusPublisher,
        tools: list[str],
        resources: list[str],
    ) -> None:
        while True:
            await asyncio.sleep(10)
            await publisher.publish(tools, resources)

    asyncio.run(_run_stdio_with_status())

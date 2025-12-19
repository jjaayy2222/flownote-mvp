# backend/mcp/server.py

"""
FlowNote MCP Server
External AI agents can use FlowNote capabilities as Tools and access Resources.
"""

import json
import asyncio
import threading
import logging
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

# FlowNote Internal Services
from backend.classifier.hybrid_classifier import HybridClassifier
from backend.faiss_search import FAISSRetriever
from backend.dashboard.dashboard_core import MetadataAggregator

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
    """Thread-safe lazy initialization of FAISSRetriever"""
    return _lazy_init(_retriever_ref, FAISSRetriever)
    # TODO: Persistent loading of embeddings should be implemented here or in FAISSRetriever


def get_aggregator() -> MetadataAggregator:
    return _lazy_init(_aggregator_ref, MetadataAggregator)


async def _run_blocking(fn, *args, **kwargs):
    """Helper to run blocking functions in a separate thread"""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as e:
        logger.exception(f"Error in blocking call {fn.__name__}")
        return e


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
    except Exception:
        logger.exception("Error during classification")
        return {
            "category": "Unclassified",
            "confidence": 0.0,
            "error": "classification_failed",
        }


@mcp.tool()
async def search_notes(query: str) -> Dict[str, Any]:
    """
    Search for notes using vector similarity search.

    Args:
        query: The search query.
    """
    if not query:
        return {
            "results": [],
            "error": None,
            "metadata": {"reason": "empty_query"},
        }

    result = await _run_blocking(get_retriever().search, query, k=5)

    if isinstance(result, Exception):
        return {
            "results": [],
            "error": "search_failed",
            "metadata": {"reason": "exception"},
        }

    return {
        "results": result,
        "error": None,
        "metadata": {"reason": "ok"},
    }


@mcp.tool()
async def get_automation_stats() -> Dict[str, Any]:
    """
    Get recent automation statistics (files, searches, categories).
    """
    result = await _run_blocking(get_aggregator().get_file_statistics)

    if isinstance(result, Exception):
        return {"error": "stats_retrieval_failed"}

    return result


# 2. Resources (데이터 노출)


@mcp.resource("flownote://para/projects")
async def get_projects() -> str:
    """Get list of projects/categories breakdown as JSON string"""
    result = await _run_blocking(get_aggregator().get_para_breakdown)

    if isinstance(result, Exception):
        return json.dumps({"error": "resource_retrieval_failed"})

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.resource("flownote://dashboard/summary")
async def get_dashboard_summary() -> str:
    """Get dashboard summary as JSON string"""
    result = await _run_blocking(get_aggregator().get_file_statistics)

    if isinstance(result, Exception):
        return json.dumps({"error": "resource_retrieval_failed"})

    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # Basic logging config for standalone execution
    logging.basicConfig(level=logging.INFO)
    mcp.run()

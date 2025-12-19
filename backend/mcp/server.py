# backend/mcp/server.py

"""
FlowNote MCP Server
External AI agents can use FlowNote capabilities as Tools and access Resources.
"""

import json
import asyncio
import threading
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

# FlowNote Internal Services
from backend.classifier.hybrid_classifier import HybridClassifier
from backend.faiss_search import FAISSRetriever
from backend.dashboard.dashboard_core import MetadataAggregator
from backend.database.connection import DatabaseConnection

# Initialize FastMCP
mcp = FastMCP("FlowNote MCP Server")

# Global instances (lazy loaded)
_classifier: Optional[HybridClassifier] = None
_retriever: Optional[FAISSRetriever] = None
_aggregator: Optional[MetadataAggregator] = None

# Thread-safe locks for lazy initialization
_classifier_lock = threading.Lock()
_retriever_lock = threading.Lock()
_aggregator_lock = threading.Lock()


def get_classifier() -> HybridClassifier:
    """Thread-safe lazy initialization of HybridClassifier"""
    global _classifier
    if _classifier is None:
        with _classifier_lock:
            if _classifier is None:
                _classifier = HybridClassifier()
    return _classifier


def get_retriever() -> FAISSRetriever:
    """Thread-safe lazy initialization of FAISSRetriever"""
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            if _retriever is None:
                _retriever = FAISSRetriever()
                # TODO: Persistent loading of embeddings should be implemented here or in FAISSRetriever
    return _retriever


def get_aggregator() -> MetadataAggregator:
    """Thread-safe lazy initialization of MetadataAggregator"""
    global _aggregator
    if _aggregator is None:
        with _aggregator_lock:
            if _aggregator is None:
                _aggregator = MetadataAggregator()
    return _aggregator


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
        return {"error": "Input text is required"}

    try:
        classifier = get_classifier()
        # classify method is already async in HybridClassifier
        return await classifier.classify(text)
    except Exception as e:
        return {"error": str(e), "category": "Unclassified", "confidence": 0.0}


@mcp.tool()
async def search_notes(query: str) -> List[Dict[str, Any]]:
    """
    Search for notes using vector similarity search.

    Args:
        query: The search query.
    """
    if not query:
        return []

    try:
        retriever = get_retriever()
        # Run blocking search in a thread executor to avoid blocking the event loop
        results = await asyncio.to_thread(retriever.search, query, k=5)
        return results
    except Exception as e:
        # Log unexpected errors but don't crash the server
        print(f"Error during search: {e}")
        return []


@mcp.tool()
async def get_automation_stats() -> Dict[str, Any]:
    """
    Get recent automation statistics (files, searches, categories).
    """
    try:
        aggregator = get_aggregator()
        # DB operations are blocking, run in thread
        return await asyncio.to_thread(aggregator.get_file_statistics)
    except Exception as e:
        return {"error": str(e)}


# 2. Resources (데이터 노출)


@mcp.resource("flownote://para/projects")
async def get_projects() -> str:
    """Get list of projects/categories breakdown as JSON string"""
    try:
        aggregator = get_aggregator()
        # DB operations are blocking, run in thread
        stats = await asyncio.to_thread(aggregator.get_para_breakdown)
        return json.dumps(stats, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("flownote://dashboard/summary")
async def get_dashboard_summary() -> str:
    """Get dashboard summary as JSON string"""
    try:
        aggregator = get_aggregator()
        # DB operations are blocking, run in thread
        stats = await asyncio.to_thread(aggregator.get_file_statistics)
        return json.dumps(stats, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()

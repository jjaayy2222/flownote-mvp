# backend/mcp/server.py

"""
FlowNote MCP Server
External AI agents can use FlowNote capabilities as Tools and access Resources.
"""

import json
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

# FlowNote Internal Services
from backend.classifier.hybrid_classifier import HybridClassifier
from backend.faiss_search import FAISSRetriever
from backend.dashboard.dashboard_core import MetadataAggregator

# Initialize FastMCP
mcp = FastMCP("FlowNote MCP Server")

# Global instances (lazy loaded)
_classifier: Optional[HybridClassifier] = None
_retriever: Optional[FAISSRetriever] = None
_aggregator: Optional[MetadataAggregator] = None

def get_classifier() -> HybridClassifier:
    global _classifier
    if _classifier is None:
        _classifier = HybridClassifier()
    return _classifier

def get_retriever() -> FAISSRetriever:
    global _retriever
    if _retriever is None:
        _retriever = FAISSRetriever()
        # Note: In a real implementation, we would load existing embeddings here.
        # Currently, FAISSRetriever starts empty in memory.
    return _retriever

def get_aggregator() -> MetadataAggregator:
    global _aggregator
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
    classifier = get_classifier()
    # classify method is async in HybridClassifier
    return await classifier.classify(text)

@mcp.tool()
async def search_notes(query: str) -> List[Dict[str, Any]]:
    """
    Search for notes using vector similarity search.
    
    Args:
        query: The search query.
    """
    retriever = get_retriever()
    # Sync method in FAISSRetriever
    results = retriever.search(query, k=5)
    return results

@mcp.tool()
async def get_automation_stats() -> Dict[str, Any]:
    """
    Get recent automation statistics (files, searches, categories).
    """
    aggregator = get_aggregator()
    return aggregator.get_file_statistics()

# 2. Resources (데이터 노출)

@mcp.resource("flownote://para/projects")
def get_projects() -> str:
    """Get list of projects/categories breakdown as JSON string"""
    aggregator = get_aggregator()
    stats = aggregator.get_para_breakdown()
    return json.dumps(stats, ensure_ascii=False, indent=2)

@mcp.resource("flownote://dashboard/summary")
def get_dashboard_summary() -> str:
    """Get dashboard summary as JSON string"""
    aggregator = get_aggregator()
    stats = aggregator.get_file_statistics()
    return json.dumps(stats, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    mcp.run()

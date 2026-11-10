"""End-to-end smoke coverage for the mounted hybrid search API."""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_current_user
from backend.main import app
from backend.services import hybrid_search_service as hybrid_search_module
from backend.services.hybrid_search_service import (
    HybridSearchService,
    get_hybrid_search_service,
)
from backend.utils import check_metadata_match


class SmokeSearchRetriever:
    """Deterministic in-memory retriever for exercising the real search pipeline."""

    def __init__(self, documents: List[Dict[str, Any]]) -> None:
        self.documents = documents
        self.queries: List[str] = []

    def search(
        self,
        query: str,
        k: int,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        self.queries.append(query)
        matches = [
            document
            for document in self.documents
            if check_metadata_match(document.get("metadata"), metadata_filter)
        ]
        return matches[:k]


@pytest.fixture
def search_api_client(monkeypatch: pytest.MonkeyPatch):
    """Run requests through the main FastAPI app and real HybridSearchService."""
    documents = [
        {
            "content": "Synthetic search smoke result",
            "metadata": {
                "id": "smoke-document",
                "category": "Projects",
                "source": "synthetic-fixture",
            },
            "score": 1.0,
        }
    ]
    faiss_retriever = SmokeSearchRetriever(documents)
    bm25_retriever = SmokeSearchRetriever(documents)
    service = HybridSearchService(
        faiss_retriever=faiss_retriever,
        bm25_retriever=bm25_retriever,
    )

    monkeypatch.setattr(
        hybrid_search_module.search_cache_service,
        "get_results",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        hybrid_search_module.search_cache_service,
        "set_results",
        AsyncMock(return_value=None),
    )
    monkeypatch.setitem(
        app.dependency_overrides, get_hybrid_search_service, lambda: service
    )
    # An anonymous request avoids recording any user-specific search history.
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: {})

    with TestClient(app) as client:
        yield client, faiss_retriever, bm25_retriever


def test_hybrid_search_api_returns_results_end_to_end(search_api_client):
    client, faiss_retriever, bm25_retriever = search_api_client

    response = client.post(
        "/search/hybrid",
        json={"query": "release checklist", "category": "Projects", "k": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["query"] == "release checklist"
    assert payload["count"] == 1
    assert payload["results"][0]["content"] == "Synthetic search smoke result"
    assert payload["results"][0]["metadata"]["category"] == "Projects"
    assert payload["applied_filter"] == {"category": "Projects"}
    assert faiss_retriever.queries == ["release checklist"]
    assert bm25_retriever.queries == ["release checklist"]

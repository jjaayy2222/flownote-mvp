"""End-to-end smoke coverage for the mounted hybrid search API."""

from typing import Any, Dict, Iterator, List, Optional, Tuple
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import create_access_token
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
        self.calls: List[Dict[str, Any]] = []

    def search(
        self,
        query: str,
        k: int,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        self.calls.append({"query": query, "k": k, "metadata_filter": metadata_filter})
        matches = [
            document
            for document in self.documents
            if check_metadata_match(document.get("metadata"), metadata_filter)
        ]
        return matches[:k]


@pytest.fixture
def search_api_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[
    Tuple[
        TestClient,
        SmokeSearchRetriever,
        SmokeSearchRetriever,
        str,
        HybridSearchService,
    ]
]:
    """Run requests through the main FastAPI app and real HybridSearchService."""
    documents = [
        {
            "content": "Shared project search result",
            "metadata": {
                "id": "shared-project",
                "category": "Projects",
                "source": "synthetic-fixture",
            },
            "score": 1.0,
        },
        {
            "content": "Dense-ranked project search result",
            "metadata": {
                "id": "dense-project",
                "category": "Projects",
                "source": "synthetic-fixture",
            },
            "score": 0.9,
        },
        {
            "content": "Sparse-ranked project search result",
            "metadata": {
                "id": "sparse-project",
                "category": "Projects",
                "source": "synthetic-fixture",
            },
            "score": 0.8,
        },
        {
            "content": "Non-project search result",
            "metadata": {
                "id": "area-result",
                "category": "Areas",
                "source": "synthetic-fixture",
            },
            "score": 0.7,
        },
    ]
    faiss_retriever = SmokeSearchRetriever(
        [documents[0], documents[3], documents[1], documents[2]]
    )
    bm25_retriever = SmokeSearchRetriever(
        [documents[2], documents[3], documents[0], documents[1]]
    )
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
    # Keep this authenticated E2E isolated from persistent search-history storage.
    monkeypatch.setattr(hybrid_search_module, "_log_search_history_bg", AsyncMock())
    monkeypatch.setitem(
        app.dependency_overrides, get_hybrid_search_service, lambda: service
    )
    access_token = create_access_token(
        {"id": "search-smoke-user", "username": "search-smoke", "role": "user"}
    )

    with TestClient(app) as client:
        yield client, faiss_retriever, bm25_retriever, access_token, service


def test_hybrid_search_api_rejects_missing_bearer_token(search_api_client):
    client, faiss_retriever, bm25_retriever, _, _ = search_api_client

    response = client.post(
        "/search/hybrid",
        json={"query": "release checklist", "category": "Projects"},
    )

    assert response.status_code in {401, 403}
    assert faiss_retriever.calls == []
    assert bm25_retriever.calls == []


def test_hybrid_search_api_returns_results_end_to_end(search_api_client):
    client, faiss_retriever, bm25_retriever, access_token, service = search_api_client
    dense_weight = 0.75

    response = client.post(
        "/search/hybrid",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "query": "release checklist",
            "category": "Projects",
            "alpha": dense_weight,
            "k": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["query"] == "release checklist"
    assert payload["count"] == 3
    results = payload["results"]
    assert [result["id"] for result in results] == [
        "shared-project",
        "dense-project",
        "sparse-project",
    ]
    assert all(result["metadata"]["category"] == "Projects" for result in results)
    assert all(result["id"] != "area-result" for result in results)
    assert payload["applied_filter"] == {"category": "Projects"}
    assert faiss_retriever.calls[0]["query"] == "release checklist"
    assert bm25_retriever.calls[0]["query"] == "release checklist"
    assert faiss_retriever.calls[0]["metadata_filter"] == {"category": "Projects"}
    assert bm25_retriever.calls[0]["metadata_filter"] == {"category": "Projects"}

    reciprocal_rank_k = service.searcher.rrf_k
    expected_scores = {
        "shared-project": dense_weight / (reciprocal_rank_k + 1)
        + (1 - dense_weight) / (reciprocal_rank_k + 2),
        "dense-project": dense_weight / (reciprocal_rank_k + 2)
        + (1 - dense_weight) / (reciprocal_rank_k + 3),
        "sparse-project": dense_weight / (reciprocal_rank_k + 3)
        + (1 - dense_weight) / (reciprocal_rank_k + 1),
    }
    for result in results:
        assert result["score"] == pytest.approx(expected_scores[result["id"]])

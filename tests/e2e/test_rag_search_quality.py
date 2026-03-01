# tests/e2e/test_rag_search_quality.py

import logging
import pytest
from typing import List, Dict, Any
from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever
from backend.services.hybrid_search_service import HybridSearchService
from backend.api.models import PARACategory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample Data: Obsidian-like Vault
SAMPLE_DOCS = [
    {
        "content": "FlowNote backend implementation plan for RAG API integration. Tasks: OpenAI embedding, Hybrid search service, E2E tests.",
        "metadata": {"source": "Projects/FlowNote/Plan.md", "category": "Projects"},
    },
    {
        "content": "Daily workout routine: 30 minutes of cardio and 20 minutes of strength training. Focus on consistency.",
        "metadata": {"source": "Areas/Health/Workout.md", "category": "Areas"},
    },
    {
        "content": "FastAPI documentation summary: Async support, Pydantic validation, Automatic OpenAPI generation.",
        "metadata": {"source": "Resources/Tech/FastAPI.md", "category": "Resources"},
    },
    {
        "content": "Old project notes from 2023. This is now deprecated and archived.",
        "metadata": {"source": "Archives/OldProject/Notes.md", "category": "Archives"},
    },
    {
        "content": "RAG (Retrieval-Augmented Generation) uses both vector search and keyword search for better accuracy.",
        "metadata": {"source": "Resources/AI/RAG_Basics.md", "category": "Resources"},
    },
    {
        "content": "Meeting notes for FlowNote: Discussed filter_expansion_factor tuning for hybrid search.",
        "metadata": {
            "source": "Projects/FlowNote/Meeting_20240301.md",
            "category": "Projects",
        },
    },
]

# Ground Truth for Evaluation: (Query -> Dict with Expected Sources and Optional Category)
GROUND_TRUTH = {
    "FlowNote RAG": {
        "sources": [
            "Projects/FlowNote/Plan.md",
            "Projects/FlowNote/Meeting_20240301.md",
            "Resources/AI/RAG_Basics.md",
        ],
        "category": PARACategory.PROJECTS,
    },
    "Health and workout": {
        "sources": ["Areas/Health/Workout.md"],
        "category": PARACategory.AREAS,
    },
    "Documentation for FastAPI": {
        "sources": ["Resources/Tech/FastAPI.md"],
        "category": PARACategory.RESOURCES,
    },
    "filter_expansion_factor": {
        "sources": ["Projects/FlowNote/Meeting_20240301.md"],
        "category": PARACategory.PROJECTS,
    },
}


@pytest.mark.skip(reason="Requires real OpenAI API Credit")
@pytest.mark.e2e
def test_rag_quality_and_tuning(embedding_dim):
    """
    실제 임베딩을 사용하여 검색 품질(P/R) 측정 및 expansion_factor 튜닝 시뮬레이션
    """
    logger.info("Starting RAG Quality E2E Test with Real Embeddings...")

    # 1. Initialize retrievers with real embeddings
    faiss_ret = FAISSRetriever(dimension=embedding_dim)
    bm25_ret = BM25Retriever()
    embedder = faiss_ret.embedding_generator

    # 2. Index documents
    logger.info(f"Generating embeddings for {len(SAMPLE_DOCS)} documents...")
    texts = [doc["content"] for doc in SAMPLE_DOCS]
    emb_result = embedder.generate_embeddings(texts)
    embeddings = emb_result["embeddings"]

    faiss_ret.add_documents(embeddings=embeddings, documents=SAMPLE_DOCS)
    bm25_ret.add_documents(SAMPLE_DOCS)

    # 3. Initialize Service
    service = HybridSearchService(faiss_retriever=faiss_ret, bm25_retriever=bm25_ret)

    # 4. Evaluate with different expansion factors
    expansion_factors = [1, 2, 5, 10]

    results_summary = []

    for factor in expansion_factors:
        logger.info(f"\nEvaluating with filter_expansion_factor={factor}")

        total_precision = 0.0
        total_recall = 0.0

        for query, gd in GROUND_TRUTH.items():
            expected_sources = gd["sources"]
            target_category = gd.get("category")

            # Perform search (k=3 for testing)
            search_result = service.search(
                query=query,
                k=3,
                filter_expansion_factor=factor,
                category=target_category,
            )

            retrieved_sources = [
                doc["metadata"]["source"] for doc in search_result.results
            ]

            # Calculate Precision and Recall
            hits = [src for src in retrieved_sources if src in expected_sources]

            p = len(hits) / len(retrieved_sources) if retrieved_sources else 0.0
            r = len(hits) / len(expected_sources) if expected_sources else 0.0

            total_precision += p
            total_recall += r

            logger.info(
                f"Query: {query} -> Hits: {len(hits)}/{len(expected_sources)}, P={p:.2f}, R={r:.2f}"
            )

        avg_p = total_precision / len(GROUND_TRUTH)
        avg_r = total_recall / len(GROUND_TRUTH)

        results_summary.append(
            {"factor": factor, "avg_precision": avg_p, "avg_recall": avg_r}
        )

        logger.info(
            f"Summary for factor {factor}: Avg P={avg_p:.2f}, Avg R={avg_r:.2f}"
        )

    # 5. Output Final Comparison
    print("\n" + "=" * 50)
    print("RAG Search Quality (filter_expansion_factor Tuning)")
    print("=" * 50)
    print(f"{'Factor':<10} | {'Avg Precision':<15} | {'Avg Recall':<15}")
    print("-" * 50)
    for res in results_summary:
        print(
            f"{res['factor']:<10} | {res['avg_precision']:<15.2f} | {res['avg_recall']:<15.2f}"
        )
    print("=" * 50)

    # 6. Basic Assertion: Recall should not decrease with higher expansion factor
    # (Note: In this small sample, it might stay same)
    assert results_summary[-1]["avg_recall"] >= results_summary[0]["avg_recall"]

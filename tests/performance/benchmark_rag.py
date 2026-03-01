# tests/performance/benchmark_rag.py

import asyncio
import time
import logging
import random
import sys
import os
from pathlib import Path
from typing import List, Dict

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from backend.services.hybrid_search_service import HybridSearchService
from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


async def run_benchmark():
    """
    RAG 검색 성능 벤치마크 및 영속화/캐싱 테스트
    """
    # 1. 시뮬레이션 데이터 준비 (1,000+ 문서)
    num_docs = 1100
    logger.info(f"Preparing {num_docs} simulated documents...")

    docs = []
    for i in range(num_docs):
        docs.append(
            {
                "content": f"FlowNote document {i}. This is a simulated content for RAG performance testing. Topic: {i % 20}",
                "metadata": {
                    "source": f"doc_{i}.md",
                    "category": random.choice(
                        ["Projects", "Areas", "Resources", "Archives"]
                    ),
                },
            }
        )

    dim = 1536
    # 가짜 임베딩 생성 (실제 API 호출 방지)
    embeddings = np.random.rand(num_docs, dim).astype("float32")

    # 2. 인덱싱 성능 측정
    logger.info("Starting Indexing Benchmark...")
    faiss_ret = FAISSRetriever(dimension=dim)
    bm25_ret = BM25Retriever()

    start_time = time.time()
    faiss_ret.add_documents(embeddings, docs)
    bm25_ret.add_documents(docs)
    indexing_time = time.time() - start_time
    logger.info(f"✅ Indexing ({num_docs} docs) took: {indexing_time:.4f}s")

    # 3. 서비스 초기화 및 영속화 테스트
    service = HybridSearchService(faiss_retriever=faiss_ret, bm25_retriever=bm25_ret)

    logger.info("Benchmark: Saving indices to disk...")
    start_time = time.time()
    service.save_indices()
    save_time = time.time() - start_time
    logger.info(f"✅ Saving took: {save_time:.4f}s")

    logger.info("Benchmark: Loading indices into a new service instance...")
    new_service = HybridSearchService(faiss_dimension=dim)
    start_time = time.time()
    new_service.load_indices()
    load_time = time.time() - start_time
    logger.info(f"✅ Loading took: {load_time:.4f}s")

    # 4. 검색 성능 측정
    query = "FlowNote topic 5 performance"
    logger.info(f"Starting Search Benchmark with query: '{query}'")

    # Case A: Initial Search (Direct Search)
    start_time = time.time()
    res1 = await service.search(query, k=5)
    first_search_time = time.time() - start_time
    logger.info(f"✅ First Search (Cache Miss/Direct) took: {first_search_time:.4f}s")

    # Case B: Repeated Search (Cache Hit if Redis is up)
    start_time = time.time()
    res2 = await service.search(query, k=5)
    second_search_time = time.time() - start_time
    logger.info(f"✅ Second Search (Cache Hit?) took: {second_search_time:.4f}s")

    if second_search_time < first_search_time:
        logger.info(
            f"🚀 Cache Speed-up: {first_search_time / second_search_time:.1f}x faster"
        )
    else:
        logger.info("ℹ️ Cache speed-up not significant or Redis not connected.")

    # 5. 다중 쿼리 부하 테스트 (Avg Latency)
    num_queries = 50
    logger.info(f"Performing {num_queries} sequential searches...")
    start_time = time.time()
    for i in range(num_queries):
        await service.search(f"topic {i % 20}", k=5)
    total_latency = time.time() - start_time
    avg_latency = total_latency / num_queries
    logger.info(f"✅ Average search latency: {avg_latency:.4f}s")
    logger.info(
        f"✅ Total TPS (sequential): {num_queries / total_latency:.2f} queries/sec"
    )

    logger.info("=" * 50)
    logger.info("Benchmark Results Summary")
    logger.info("-" * 50)
    logger.info(f"Documents Indexed: {num_docs}")
    logger.info(f"Indexing Time:    {indexing_time:.4f}s")
    logger.info(f"Persistence Save: {save_time:.4f}s")
    logger.info(f"Persistence Load: {load_time:.4f}s")
    logger.info(f"Avg Latency:      {avg_latency:.4f}s")
    logger.info("=" * 50)


if __name__ == "__main__":
    try:
        asyncio.run(run_benchmark())
    except Exception as e:
        logger.error(f"Benchmark failed: {e}", exc_info=True)

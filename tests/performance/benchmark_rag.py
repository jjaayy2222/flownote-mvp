# tests/performance/benchmark_rag.py

import asyncio
import time
import logging
import random
import sys
import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
from unittest.mock import MagicMock, AsyncMock, patch

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from backend.services.hybrid_search_service import HybridSearchService
from backend.faiss_search import FAISSRetriever
from backend.bm25_search import BM25Retriever
from backend.services.chat_service import ChatService
from backend.services.chat_history_service import ChatHistoryService
from backend.services.onboarding_service import OnboardingService
from backend.api.models import ChatMessage
from tests.performance.collector import measure_stream_performance

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)




async def run_load_test(chat_service: ChatService, queries: List[str], concurrency: int = 5):
    """
    동시성 제어를 포함한 부하 테스트를 수행합니다.
    """
    logger.info(f"Starting Load Test: Concurrency={concurrency}, Total Queries={len(queries)}")
    
    semaphore = asyncio.Semaphore(concurrency)
    
    async def task(query):
        async with semaphore:
            return await measure_stream_performance(chat_service, query)

    start_time = time.perf_counter()
    tasks = [task(q) for q in queries]
    # return_exceptions=True를 적용하여 개별 에러가 전체 벤치마크를 중단시키지 않도록 방어
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_duration = time.perf_counter() - start_time

    # 에러 결과와 성공 결과 분리
    actual_results = []
    errors = []
    for r in results:
        if isinstance(r, Exception):
            errors.append(r)
        else:
            actual_results.append(r)

    # 통계 계산
    successful_results = [r for r in actual_results if r["success"]]
    ttfts = [r["ttft"] for r in successful_results if r["ttft"] is not None]
    total_times = [r["total_time"] for r in successful_results if r["total_time"] is not None]

    avg_ttft = np.mean(ttfts) if ttfts else 0
    p95_ttft = np.percentile(ttfts, 95) if ttfts else 0
    avg_total_time = np.mean(total_times) if total_times else 0
    tps = len(successful_results) / total_duration if total_duration > 0 else 0

    logger.info("=" * 50)
    logger.info("LOAD TEST RESULTS")
    logger.info("-" * 50)
    logger.info(f"Concurrency:      {concurrency}")
    logger.info(f"Total Queries:    {len(queries)}")
    logger.info(f"Success Count:    {len(successful_results)}")
    if ttfts:
        logger.info(f"Avg TTFT:         {avg_ttft:.4f}s")
        logger.info(f"P95 TTFT:         {p95_ttft:.4f}s")
    if total_times:
        logger.info(f"Avg Total Time:   {avg_total_time:.4f}s")
    logger.info(f"System Throughput: {tps:.2f} queries/sec")
    logger.info(f"Total Duration:   {total_duration:.2f}s")
    
    # [Robustness] 에러 요약 로깅 (Review 반영)
    if errors or len(actual_results) > len(successful_results):
        failed_internal = len(actual_results) - len(successful_results)
        logger.warning(
            f"Partial failures detected: Exceptions={len(errors)}, "
            f"Logical failures={failed_internal}"
        )
        if errors:
            first_err = errors[0]
            err_msg = str(first_err)
            # [Performance] 요약 로그는 간결하게 유지 (100자 제한)
            truncated_msg = (err_msg[:100] + '...') if len(err_msg) > 100 else err_msg
            logger.error(f"First error summary: {repr(first_err)[:50]}... msg={truncated_msg}")
            logger.debug("Full error traceback", exc_info=first_err)
            
    logger.info("=" * 50)


def setup_mock_llm():
    """
    실제 API 호출 없이 벤치마크 로직을 검증하기 위한 Mock LLM 설정
    """
    from langchain_core.outputs import ChatGenerationChunk
    from langchain_core.messages import AIMessageChunk
    
    mock_llm = MagicMock()
    
    async def mock_astream(*args, **kwargs):
        # 가짜 토큰 스트리밍 시뮬레이션
        tokens = ["This ", "is ", "a ", "mocked ", "response ", "for ", "performance ", "testing."]
        await asyncio.sleep(0.1) # Initial delay (TTFT)
        for token in tokens:
            yield AIMessageChunk(content=token)
            await asyncio.sleep(0.02) # Inter-token delay

    async def mock_ainvoke(*args, **kwargs):
        return AIMessageChunk(content="Mocked standalone response")

    mock_llm.astream = mock_astream
    mock_llm.ainvoke = mock_ainvoke
    mock_llm.invoke = MagicMock(side_effect=lambda *a, **k: AIMessageChunk(content="Mocked response"))
    return mock_llm


async def run_benchmark(use_mock_llm: bool = True):
    """
    RAG 시스템 종합 벤치마크 (검색 + 서비스 레이어)
    """
    # 1. 시뮬레이션 데이터 및 서비스 초기화
    num_docs = 500
    dim = 1536
    
    logger.info(f"Initializaing services with {num_docs} docs...")
    faiss_ret = FAISSRetriever(dimension=dim)
    bm25_ret = BM25Retriever()
    
    docs = [
        {
            "content": f"FlowNote document {i}. Topic: {i % 10}",
            "metadata": {"source": f"doc_{i}.md", "id": str(i)}
        } for i in range(num_docs)
    ]
    fake_embeddings = np.random.rand(num_docs, dim).astype("float32")
    faiss_ret.add_documents(fake_embeddings, docs)
    bm25_ret.add_documents(docs)
    
    hybrid_search = HybridSearchService(faiss_retriever=faiss_ret, bm25_retriever=bm25_ret)
    
    # Mock 의존성 설정
    mock_onboarding = MagicMock(spec=OnboardingService)
    mock_onboarding.get_user_status.return_value = {"status": "success", "is_completed": True, "occupation": "Researcher", "areas": ["AI"]}
    
    mock_history = AsyncMock(spec=ChatHistoryService)
    mock_history.get_history.return_value = []
    
    # [Security] API Key mock
    os.environ["GPT4O_MINI_API_KEY"] = os.getenv("GPT4O_MINI_API_KEY") or "mock-key"
    os.environ["RAG_MAX_DOCS"] = "5"
    
    mock_llm = None
    if use_mock_llm:
        logger.info("Using Mock LLM for benchmark logic validation.")
        mock_llm = setup_mock_llm()

    chat_service = ChatService(
        hybrid_search_service=hybrid_search,
        onboarding_service=mock_onboarding,
        chat_history_service=mock_history,
        llm=mock_llm,
        streaming_llm=mock_llm
    )

    # 2. 단일 스트리밍 성능 측정 (TTFT Focus)
    logger.info("Benchmark: Measuring Single Stream Performance...")
    perf_result = await measure_stream_performance(chat_service, "Tell me about FlowNote performance")
    if perf_result["success"] and perf_result["ttft"] is not None:
        logger.info(f"✅ Single TTFT: {perf_result['ttft']:.4f}s")
        logger.info(f"✅ Single Total: {perf_result['total_time']:.4f}s")
        logger.info(f"✅ Chunks count: {perf_result['chunks_count']}")
        logger.info(f"✅ CPS: {perf_result['cps']:.2f} chunks/sec")
    else:
        logger.warning(f"❌ Single stream test failed or returned no tokens. Error: {perf_result.get('error')}")
    
    # 3. 동시 부하 테스트
    load_queries = [f"Performance test query {i}" for i in range(10)]
    await run_load_test(chat_service, load_queries, concurrency=3)


if __name__ == "__main__":
    # 환경변수에 실제 키가 있으면 실제 LLM 사용, 없으면 Mock 사용
    api_key_exists = bool(os.getenv("GPT4O_MINI_API_KEY") or os.getenv("OPENAI_API_KEY"))
    
    try:
        asyncio.run(run_benchmark(use_mock_llm=not api_key_exists))
    except Exception as e:
        logger.error(f"Benchmark failed: {e}", exc_info=True)

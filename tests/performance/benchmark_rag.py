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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


async def measure_stream_performance(
    chat_service: ChatService, 
    query: str, 
    user_id: str = "test_user",
    session_id: Optional[str] = None
) -> Dict:
    """
    stream_chat을 호출하여 TTFT 및 전체 지연 시간을 측정합니다.
    """
    start_time = time.perf_counter()
    ttft = None
    total_time = None
    first_chunk_received = False
    chunks_count = 0
    chars_count = 0
    full_response = ""

    try:
        async for sse_event in chat_service.stream_chat(
            query=query, 
            user_id=user_id, 
            session_id=session_id
        ):
            # sse_event는 "data: {...}\n\n" 형식임
            if sse_event.startswith("data: "):
                data_str = sse_event[6:].strip()
                if data_str == "[DONE]":
                    break
                
                try:
                    event_data = json.loads(data_str)
                    event_type = event_data.get("type")
                    
                    if event_type == "token":
                        if not first_chunk_received:
                            ttft = time.perf_counter() - start_time
                            first_chunk_received = True
                        
                        chunks_count += 1
                        chunk_content = event_data.get("content", "")
                        chars_count += len(chunk_content)
                        full_response += chunk_content
                except json.JSONDecodeError:
                    continue

        total_time = time.perf_counter() - start_time
        stream_duration = total_time - (ttft or 0)
        
        return {
            "query": query,
            "ttft": ttft,
            "total_time": total_time,
            "chunks_count": chunks_count,
            "chars_count": chars_count,
            "cps": chunks_count / stream_duration if stream_duration > 0 else 0,
            "chars_per_sec": chars_count / stream_duration if stream_duration > 0 else 0,
            "success": True
        }
    except Exception as e:
        logger.error(f"Stream performance measurement failed: {e}")
        return {"query": query, "success": False, "error": str(e), "ttft": None, "total_time": None}


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
    results = await asyncio.gather(*tasks)
    total_duration = time.perf_counter() - start_time

    # 통계 계산
    successful_results = [r for r in results if r["success"]]
    ttfts = [r["ttft"] for r in successful_results if r["ttft"] is not None]
    total_times = [r["total_time"] for r in successful_results if r["total_time"] is not None]

    avg_ttft = np.mean(ttfts) if ttfts else 0
    p95_ttft = np.percentile(ttfts, 95) if ttfts else 0
    avg_total_time = np.mean(total_times) if total_times else 0
    tps = len(successful_results) / total_duration if total_duration > 0 else 0

    logger.info("=" * 50)
    logger.info("🚀 LOAD TEST RESULTS")
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
        await asyncio.sleep(0.2) # Initial delay (TTFT)
        for token in tokens:
            yield AIMessageChunk(content=token)
            await asyncio.sleep(0.05) # Inter-token delay

    mock_llm.astream = mock_astream
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

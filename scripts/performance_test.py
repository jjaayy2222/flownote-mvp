# scripts/performance_test.py

import asyncio
import time
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, AsyncMock
from backend.services.classification_service import ClassificationService
from backend.services.rule_engine import RuleResult


async def benchmark():
    print("🚀 Starting HybridClassifier Performance Benchmark...")
    print("--------------------------------------------------")

    try:
        service = ClassificationService()

        # 1. Benchmark Rule Hit
        print("\n[Scenario 1] Rule Hit (Fast Path)")
        # Force Rule Match
        mock_rule_engine = MagicMock()
        mock_rule_engine.evaluate.return_value = RuleResult(
            category="Projects", confidence=1.0, matched_rule="perf_rule"
        )
        service.hybrid_classifier.rule_engine = mock_rule_engine

        # Ensure AI is mock (should not be called)
        service.hybrid_classifier.ai_classifier = MagicMock()
        service.hybrid_classifier.ai_classifier.classify = AsyncMock()

        start_time = time.time()
        iterations = 100
        for _ in range(iterations):
            await service.classify("test text", user_id="bench_user")
        duration = time.time() - start_time
        print(f"  - Total Time ({iterations} req): {duration:.4f}s")
        print(f"  - Avg Latency: {duration/iterations*1000:.2f}ms")
        print(f"  - Throughput: {iterations/duration:.2f} req/s")

        # 2. Benchmark AI Fallback (Latency Simulated)
        print("\n[Scenario 2] AI Fallback (Simulated 10ms Latency)")
        # Force Rule Miss
        mock_rule_engine.evaluate.return_value = None

        # Mock AI with delay
        async def delayed_ai(*args, **kwargs):
            await asyncio.sleep(0.01)  # 10ms simulated latency
            return {"category": "Areas", "confidence": 0.9, "method": "ai"}

        service.hybrid_classifier.ai_classifier.classify = delayed_ai

        start_time = time.time()
        for _ in range(iterations):
            await service.classify("test text", user_id="bench_user")
        duration = time.time() - start_time
        print(f"  - Total Time ({iterations} req): {duration:.4f}s")
        print(f"  - Avg Latency: {duration/iterations*1000:.2f}ms")
        print(f"  - Throughput: {iterations/duration:.2f} req/s")

        print("\n✅ Benchmark Complete.")

    except Exception as e:
        print(f"❌ Benchmark Failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(benchmark())

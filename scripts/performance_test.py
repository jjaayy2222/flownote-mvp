# scripts/performance_test.py

import asyncio
import time
import argparse
from unittest.mock import MagicMock, AsyncMock
from backend.services.classification_service import ClassificationService
from backend.services.rule_engine import RuleResult


async def run_scenario(name, service, iterations, setup_func=None):
    """Execute a single benchmark scenario."""
    if setup_func:
        setup_func(service)

    print(f"\n[Scenario] {name}")
    start_time = time.time()
    for _ in range(iterations):
        await service.classify("test text", user_id="bench_user")
    duration = time.time() - start_time

    avg_latency_ms = duration / iterations * 1000
    throughput = iterations / duration
    print(f"  - Total Time ({iterations} req): {duration:.4f}s")
    print(f"  - Avg Latency: {avg_latency_ms:.2f}ms")
    print(f"  - Throughput: {throughput:.2f} req/s")


def setup_rule_hit(service):
    """Configure service for Rule Hit scenario."""
    mock_rule = MagicMock()
    mock_rule.evaluate.return_value = RuleResult(
        category="Projects", confidence=1.0, matched_rule="perf_rule"
    )
    # Inject mock into the rule engine instance used by hybrid classifier
    service.hybrid_classifier.rule_engine = mock_rule
    # Ensure AI is mock and strictly not called
    service.hybrid_classifier.ai_classifier.classify = AsyncMock()


def setup_ai_fallback(service, latency):
    """Configure service for AI Fallback scenario with simulated latency."""
    # Force Rule Miss
    mock_rule = MagicMock()
    mock_rule.evaluate.return_value = None
    service.hybrid_classifier.rule_engine = mock_rule

    # Mock AI with delay
    async def delayed_ai(*args, **kwargs):
        if latency > 0:
            await asyncio.sleep(latency)
        return {"category": "Areas", "confidence": 0.9, "method": "ai"}

    service.hybrid_classifier.ai_classifier.classify = delayed_ai


async def main():
    """
    Manual performance benchmark for HybridClassifier.

    Usage:
        python -m scripts.performance_test --iterations 500 --latency 0.05

    Note:
        This script is intended for ad-hoc, local performance exploration and is
        not run as part of the automated CI test suite.
    """
    parser = argparse.ArgumentParser(
        description="HybridClassifier Performance Benchmark"
    )
    parser.add_argument(
        "--iterations", type=int, default=100, help="Number of requests per scenario"
    )
    parser.add_argument(
        "--latency",
        type=float,
        default=0.01,
        help="Simulated AI latency in seconds (default: 0.01s)",
    )
    args = parser.parse_args()

    print("🚀 Starting HybridClassifier Performance Benchmark...")
    print(f"   Iterations: {args.iterations}, AI Latency: {args.latency*1000}ms")
    print("--------------------------------------------------")

    try:
        # Initialize service (Mocking external deps if needed could be done here too)
        service = ClassificationService()
        # Mock _save_results to avoid I/O noise in benchmark
        service._save_results = MagicMock(return_value={})

        # Scenario 1: Rule Hit
        await run_scenario(
            "Rule Hit (Fast Path)", service, args.iterations, setup_rule_hit
        )

        # Scenario 2: AI Fallback
        await run_scenario(
            f"AI Fallback (Simulated {args.latency*1000:.1f}ms Latency)",
            service,
            args.iterations,
            lambda s: setup_ai_fallback(s, args.latency),
        )

        print("\n✅ Benchmark Complete.")

    except Exception as e:
        print(f"❌ Benchmark Failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())

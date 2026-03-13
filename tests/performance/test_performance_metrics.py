# tests/performance/test_performance_metrics.py

import pytest
import json
import asyncio
from typing import List, AsyncGenerator
from unittest.mock import MagicMock

# benchmark_rag에서 measure_stream_performance를 가져오기 위해 상위 경로 추가가 필요할 수 있음
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.performance.benchmark_rag import measure_stream_performance

class FakeChatService:
    """
    Fake chat_service implementation for unit-testing measure_stream_performance.
    """
    def __init__(self, events: List[str]) -> None:
        self._events = events

    async def stream_chat(
        self,
        query: str,
        user_id: str,
        session_id: str = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        for event in self._events:
            yield event
            await asyncio.sleep(0.01) # 가짜 딜레이

@pytest.mark.asyncio
async def test_measure_stream_performance_basic_stream_metrics():
    """
    정상적인 토큰 이벤트 자열이 전달될 때 지표 집계가 올바른지 검증
    """
    events = [
        'data: {"type": "token", "content": "Hello"}\n\n',
        'data: {"type": "token", "content": " world"}\n\n',
        'data: [DONE]\n\n',
    ]
    fake_service = FakeChatService(events)
    
    result = await measure_stream_performance(
        chat_service=fake_service,
        query="test query",
        user_id="test_user"
    )
    
    assert result["success"] is True
    assert result["chunks_count"] == 2
    assert result["chars_count"] == len("Hello world")
    assert result["ttft"] is not None
    assert result["ttft"] > 0
    assert result["total_time"] > result["ttft"]
    assert result["cps"] > 0

@pytest.mark.asyncio
async def test_measure_stream_performance_no_token_events():
    """
    토큰 이벤트 없이 메타데이터만 오거나 바로 종료되는 경우 0으로 나누기 에러 방지 검증
    """
    events = [
        'data: {"type": "search_start"}\n\n',
        'data: [DONE]\n\n',
    ]
    fake_service = FakeChatService(events)
    
    result = await measure_stream_performance(
        chat_service=fake_service,
        query="no tokens",
        user_id="test_user"
    )
    
    assert result["success"] is True
    assert result["chunks_count"] == 0
    assert result["chars_count"] == 0
    assert result["cps"] == 0
    assert result["chars_per_sec"] == 0

@pytest.mark.asyncio
async def test_measure_stream_performance_malformed_json():
    """
    잘못된 JSON 형식이 섞여 있어도 건너뛰고 정상 동작하는지 검증
    """
    events = [
        'data: {invalid json}\n\n',
        'data: {"type": "token", "content": "Valid"}\n\n',
        'data: [DONE]\n\n',
    ]
    fake_service = FakeChatService(events)
    
    result = await measure_stream_performance(
        chat_service=fake_service,
        query="malformed json",
        user_id="test_user"
    )
    
    assert result["success"] is True
    assert result["chunks_count"] == 1
    assert result["chars_count"] == len("Valid")

# tests/performance/collector.py

import time
import json
import logging
from typing import Dict, List, Optional, Any

# ChatService 타입을 힌트로 사용하기 위해 import
# Note: 순환 참조 방지를 위해 지연 임포트(Internal)를 고려할 필요는 없음
from backend.services.chat_service import ChatService

logger = logging.getLogger(__name__)

async def measure_stream_performance(
    chat_service: ChatService, 
    query: str, 
    user_id: str = "test_user",
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    stream_chat을 호출하여 TTFT 및 전체 지연 시간을 측정합니다.
    
    [Metrics]
    - ttft: Time To First Token (첫 토큰 수신 시간)
    - total_time: 전체 스트림 종료 시간
    - chunks_count: 수신된 청크(이벤트) 수
    - chars_count: 수신된 전체 문자 수
    - cps: Chunks Per Second
    - chars_per_sec: Characters Per Second
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
                    # [Robustness] 잘못된 JSON 형식은 건너뜀 (Review 반영)
                    continue

        total_time = time.perf_counter() - start_time
        stream_duration = total_time - (ttft or 0)
        
        # [Fail Safe] Division by zero 방어
        return {
            "query": query,
            "ttft": ttft if ttft is not None else total_time,
            "total_time": total_time,
            "chunks_count": chunks_count,
            "chars_count": chars_count,
            "cps": chunks_count / stream_duration if stream_duration > 0 else 0,
            "chars_per_sec": chars_count / stream_duration if stream_duration > 0 else 0,
            "success": True
        }
    except Exception as e:
        logger.error(f"Stream performance measurement failed: {e}", exc_info=True)
        return {
            "query": query, 
            "success": False, 
            "error": str(e), 
            "ttft": None, 
            "total_time": None,
            "chunks_count": 0,
            "chars_count": 0,
            "cps": 0,
            "chars_per_sec": 0
        }

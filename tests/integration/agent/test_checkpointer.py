"""
tests/integration/agent/test_checkpointer.py

Redis Checkpointer를 사용한 LangGraph 상태 복구(Persistence) 통합 테스트.

실행 방법:
    # Redis 서버가 실행 중인지 확인
    redis-cli ping  # PONG이 나와야 함

    # 환경변수 설정 확인
    export REDIS_URL=redis://localhost:6379

    # 테스트 실행
    python -m pytest tests/integration/agent/test_checkpointer.py -v
"""

import os
import uuid
import pytest
from dotenv import load_dotenv

# 테스트 환경 변수 로드
load_dotenv()

# Redis 가용 여부 확인 (없으면 테스트 스킵)
REDIS_URL = os.getenv("REDIS_URL")
try:
    from langgraph.checkpoint.redis import ShallowRedisSaver

    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False

skip_if_no_redis = pytest.mark.skipif(
    not (_REDIS_AVAILABLE and REDIS_URL),
    reason="Redis not available (REDIS_URL not set or langgraph-checkpoint-redis not installed)",
)


@skip_if_no_redis
class TestRedisCheckpointer:
    """Redis Checkpointer를 사용한 상태 복구 테스트"""

    def test_checkpointer_initializes(self):
        """get_checkpointer()가 Redis 환경에서 RedisSaver를 반환하는지 검증"""
        from backend.agent.checkpointer import get_checkpointer

        checkpointer = get_checkpointer()

        # REDIS_URL이 설정된 환경에서는 ShallowRedisSaver가 반환되어야 함
        assert isinstance(checkpointer, ShallowRedisSaver), (
            f"Expected ShallowRedisSaver but got {type(checkpointer).__name__}. "
            "Check REDIS_URL and langgraph-checkpoint-redis installation."
        )

    def test_workflow_state_persistence_with_thread_id(self):
        """
        thread_id를 사용하여 에이전트 상태가 Redis에 저장되고 복구되는지 검증.

        시나리오:
        1. 고유한 thread_id로 워크플로우 실행 (1회차)
        2. 동일한 thread_id로 워크플로우 상태 조회 (복구)
        3. 저장된 상태가 존재하는지 확인
        """
        from backend.agent.graph import create_workflow
        from backend.agent.checkpointer import get_checkpointer

        # 고유한 thread_id 생성 (테스트 격리)
        thread_id = f"test-thread-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}}

        # Checkpointer 초기화
        checkpointer = get_checkpointer()
        workflow = create_workflow(checkpointer=checkpointer)

        # 초기 상태 정의
        initial_state = {
            "file_content": "LangGraph Persistence Test Document",
            "file_name": "test_persistence.md",
            "extracted_keywords": [],
            "retrieved_context": "",
            "retry_count": 0,
            "confidence_score": 0.0,
        }

        # 1회차 실행
        result = workflow.invoke(initial_state, config=config)

        # 실행 결과 확인
        assert result is not None, "Workflow should return a result"

        # 2회차: 동일 thread_id로 상태 복구 확인
        # get_state()로 저장된 상태를 가져옴
        saved_state = workflow.get_state(config)

        assert saved_state is not None, "State should be saved in Redis"
        assert saved_state.values is not None, "Saved state should have values"

    def test_different_threads_are_isolated(self):
        """
        서로 다른 thread_id는 독립적인 상태를 가지는지 검증 (격리성 테스트).
        """
        from backend.agent.graph import create_workflow
        from backend.agent.checkpointer import get_checkpointer

        checkpointer = get_checkpointer()
        workflow = create_workflow(checkpointer=checkpointer)

        thread_id_1 = f"test-thread-{uuid.uuid4()}"
        thread_id_2 = f"test-thread-{uuid.uuid4()}"

        state_1 = {
            "file_content": "Document for Thread 1",
            "file_name": "thread1.md",
            "extracted_keywords": [],
            "retrieved_context": "",
            "retry_count": 0,
            "confidence_score": 0.0,
        }
        state_2 = {
            "file_content": "Document for Thread 2",
            "file_name": "thread2.md",
            "extracted_keywords": [],
            "retrieved_context": "",
            "retry_count": 0,
            "confidence_score": 0.0,
        }

        # 두 개의 독립적인 스레드 실행
        workflow.invoke(state_1, config={"configurable": {"thread_id": thread_id_1}})
        workflow.invoke(state_2, config={"configurable": {"thread_id": thread_id_2}})

        # 각 스레드의 상태 복구
        saved_1 = workflow.get_state({"configurable": {"thread_id": thread_id_1}})
        saved_2 = workflow.get_state({"configurable": {"thread_id": thread_id_2}})

        # 두 상태가 독립적으로 존재해야 함
        assert saved_1 is not None
        assert saved_2 is not None
        # 두 상태의 파일명이 서로 달라야 함
        assert saved_1.values.get("file_name") != saved_2.values.get("file_name")


class TestMemorySaverFallback:
    """Redis 없이 MemorySaver로 폴백되는 경우 테스트 (항상 실행)"""

    def test_checkpointer_falls_back_to_memory_saver(self, monkeypatch):
        """REDIS_URL이 없을 때 MemorySaver로 폴백되는지 검증"""
        from langgraph.checkpoint.memory import MemorySaver
        from backend.agent.checkpointer import get_checkpointer

        # REDIS_URL 환경변수 제거
        monkeypatch.delenv("REDIS_URL", raising=False)

        checkpointer = get_checkpointer()
        assert isinstance(
            checkpointer, MemorySaver
        ), "Should fall back to MemorySaver when REDIS_URL is not set"

    def test_workflow_runs_with_memory_saver(self, monkeypatch):
        """MemorySaver로도 워크플로우가 정상 실행되는지 검증"""
        from backend.agent.graph import create_workflow
        from langgraph.checkpoint.memory import MemorySaver

        monkeypatch.delenv("REDIS_URL", raising=False)

        thread_id = f"test-memory-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}}

        # MemorySaver 직접 주입
        workflow = create_workflow(checkpointer=MemorySaver())

        initial_state = {
            "file_content": "MemorySaver Test Document",
            "file_name": "memory_test.md",
            "extracted_keywords": [],
            "retrieved_context": "",
            "retry_count": 0,
            "confidence_score": 0.0,
        }

        result = workflow.invoke(initial_state, config=config)
        assert result is not None, "Workflow should run successfully with MemorySaver"

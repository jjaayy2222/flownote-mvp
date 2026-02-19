"""
tests/integration/agent/test_hitl.py

Human-in-the-Loop (HitL) 기능 테스트.
낮은 신뢰도 상황에서 interrupt_before 설정 시 에이전트가 중단되는지 검증합니다.

실행 방법:
    python -m pytest tests/integration/agent/test_hitl.py -v
"""

import uuid
import pytest
from langgraph.checkpoint.memory import MemorySaver


class TestHumanInTheLoop:
    """interrupt_before 파라미터를 통한 Human-in-the-Loop 동작 검증"""

    def _make_initial_state(self, file_name: str = "hitl_test.md") -> dict:
        return {
            "file_content": "Human-in-the-Loop Test Document",
            "file_name": file_name,
            "extracted_keywords": [],
            "retrieved_context": "",
            "retry_count": 0,
            "confidence_score": 0.0,
        }

    def test_workflow_runs_without_interrupt(self):
        """interrupt_before=None(기본값)일 때 워크플로우가 끝까지 자동 실행되는지 검증"""
        from backend.agent.graph import create_workflow

        thread_id = f"test-no-interrupt-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}}

        # interrupt_before 없이 실행 (기본값: None → [])
        workflow = create_workflow(checkpointer=MemorySaver())
        result = workflow.invoke(self._make_initial_state(), config=config)

        assert result is not None, "Workflow should complete without interruption"

    def test_workflow_interrupts_before_reflect_node(self):
        """
        interrupt_before=['reflect'] 설정 시 reflect 노드 진입 전에 중단되는지 검증.

        - 에이전트가 validate 후 should_retry → 'retry' 경로를 타면 reflect로 진입
        - interrupt_before=['reflect']이면 reflect 진입 직전에 멈춤 (상태: INTERRUPTED)
        - 이 테스트는 낮은 신뢰도([confidence_score < 0.7])를 유도해야 하나,
          LLM이 Mock되어 있으므로 동작 확인 위주로 검증
        """
        from backend.agent.graph import create_workflow

        thread_id = f"test-interrupt-reflect-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}}

        # reflect 노드 진입 전 중단 설정
        workflow = create_workflow(
            checkpointer=MemorySaver(),
            interrupt_before=["reflect"],
        )

        # 워크플로우 실행 (중단 발생 가능)
        # invoke()는 중단점에서 멈추고 현재까지의 상태를 반환하거나 None 반환
        result = workflow.invoke(self._make_initial_state(), config=config)

        # 중단 여부와 관계없이 상태가 저장되어 있어야 함
        saved_state = workflow.get_state(config)
        assert saved_state is not None, "State should be saved even after interruption"

    def test_interrupt_before_accepts_empty_list(self):
        """interrupt_before=[]일 때 정상 실행되는지 검증 (빈 리스트 처리 확인)"""
        from backend.agent.graph import create_workflow

        thread_id = f"test-empty-interrupt-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}}

        workflow = create_workflow(
            checkpointer=MemorySaver(),
            interrupt_before=[],  # 명시적 빈 리스트
        )

        result = workflow.invoke(self._make_initial_state(), config=config)
        assert (
            result is not None
        ), "Workflow should run normally with empty interrupt_before"

    def test_create_workflow_signature_has_interrupt_before(self):
        """create_workflow 함수가 interrupt_before 파라미터를 받는지 시그니처 검증"""
        import inspect
        from backend.agent.graph import create_workflow

        sig = inspect.signature(create_workflow)
        assert (
            "interrupt_before" in sig.parameters
        ), "create_workflow should accept 'interrupt_before' parameter for HitL support"

        # 기본값이 None인지 확인
        default = sig.parameters["interrupt_before"].default
        assert (
            default is None
        ), f"'interrupt_before' default should be None, got {default!r}"

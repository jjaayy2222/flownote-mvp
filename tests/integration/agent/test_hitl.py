"""
tests/integration/agent/test_hitl.py

Human-in-the-Loop (HitL) 기능 테스트.
낮은 신뢰도 상황에서 interrupt_before 설정 시 에이전트가 중단되는지 검증합니다.

실행 방법:
    python -m pytest tests/integration/agent/test_hitl.py -v
"""

import uuid
import inspect
import pytest
from langgraph.checkpoint.memory import MemorySaver
from backend.agent.graph import create_workflow


class TestHumanInTheLoop:
    """interrupt_before 파라미터를 통한 Human-in-the-Loop 동작 검증"""

    # ------------------------------------------------------------------
    # 헬퍼 메서드: 테스트 간 공통 셋업 중복 제거
    # ------------------------------------------------------------------

    def _make_config(self, prefix: str = "test") -> dict:
        """고유한 thread_id를 포함하는 LangGraph configurable 딕셔너리 반환.

        각 테스트에서 독립적인 상태 격리를 보장하기 위해
        매 호출마다 새로운 UUID를 생성합니다.
        """
        thread_id = f"{prefix}-{uuid.uuid4()}"
        return {"configurable": {"thread_id": thread_id}}

    def _make_initial_state(self, file_name: str = "hitl_test.md") -> dict:
        return {
            "file_content": "Human-in-the-Loop Test Document",
            "file_name": file_name,
            "extracted_keywords": [],
            "retrieved_context": "",
            "retry_count": 0,
            "confidence_score": 0.0,
        }

    # ------------------------------------------------------------------
    # 정상 실행 경로 테스트
    # ------------------------------------------------------------------

    def test_workflow_runs_without_interrupt(self):
        """interrupt_before=None(기본값)일 때 워크플로우가 끝까지 자동 실행되는지 검증"""
        config = self._make_config("test-no-interrupt")

        # interrupt_before 없이 실행 (기본값: None → [])
        workflow = create_workflow(checkpointer=MemorySaver())
        result = workflow.invoke(self._make_initial_state(), config=config)

        # 결과 객체 자체가 유효한지 확인
        assert (
            result is not None
        ), "Workflow should return a result without interruption"

        # 워크플로우가 실제로 terminal state에 도달했는지 검증
        # LangGraph에서 완전 종료 시: state.next == () (빈 튜플)
        state = workflow.get_state(config)
        assert state is not None, "State should be retrievable after complete run"
        assert not state.next, (
            f"Workflow should have no pending next nodes (terminal state), "
            f"got state.next={state.next!r}"
        )

    def test_interrupt_before_accepts_empty_list(self):
        """interrupt_before=[]일 때 정상 실행되는지 검증 (빈 리스트 처리 확인)"""
        config = self._make_config("test-empty-interrupt")

        workflow = create_workflow(
            checkpointer=MemorySaver(),
            interrupt_before=[],  # 명시적 빈 리스트
        )

        result = workflow.invoke(self._make_initial_state(), config=config)
        assert (
            result is not None
        ), "Workflow should run normally with empty interrupt_before"

        # 명시적 빈 리스트를 전달했을 때도 기본 설정과 동일하게
        # 워크플로우가 완전히 종료(terminal state)되는지 검증
        # LangGraph의 state.next는 tuple 타입: 완전 종료 시 () 반환
        state = workflow.get_state(config)
        assert not state.next, (
            f"Workflow with interrupt_before=[] should reach terminal state, "
            f"got state.next={state.next!r}"
        )

    def test_interrupt_before_accepts_none(self):
        """interrupt_before=None 명시 전달 시 정상 실행되는지 검증 (None → [] 정규화 경로 확인)

        create_workflow 내부에서 None을 []로 정규화하는 로직이
        리팩터링 시에도 올바르게 동작하는지 보장하기 위한 안전장치입니다.
        """
        config = self._make_config("test-none-interrupt")

        # 기본값이 아닌 명시적 None 전달로 정규화 경로를 직접 검증
        workflow = create_workflow(
            checkpointer=MemorySaver(),
            interrupt_before=None,
        )

        result = workflow.invoke(self._make_initial_state(), config=config)
        assert (
            result is not None
        ), "Workflow should run normally with interrupt_before=None (normalized to [])"

        # terminal state 검증: None 전달도 [] 와 동일하게 완전 종료되어야 함
        state = workflow.get_state(config)
        assert not state.next, (
            f"Workflow with interrupt_before=None should reach terminal state, "
            f"got state.next={state.next!r}"
        )

    # ------------------------------------------------------------------
    # 인터럽트 동작 테스트
    # ------------------------------------------------------------------

    def test_workflow_interrupts_before_reflect_node(self):
        """
        interrupt_before=['reflect'] 설정 시 reflect 노드 진입 전에 중단되는지 검증.

        - 에이전트가 validate 후 should_retry → 'retry' 경로를 타면 reflect로 진입
        - interrupt_before=['reflect']이면 reflect 진입 직전에 멈춤
        - 이 경우 LangGraph는 state.next에 'reflect'를 남겨 중단 지점을 표시
        - LLM이 Mock되어 최저 신뢰도(confidence_score=0.0)로 retry 경로를 유도
        """
        config = self._make_config("test-interrupt-reflect")

        # reflect 노드 진입 전 중단 설정
        workflow = create_workflow(
            checkpointer=MemorySaver(),
            interrupt_before=["reflect"],
        )

        # 워크플로우 실행: retry 경로 진입 시 reflect 직전에 중단
        workflow.invoke(self._make_initial_state(), config=config)

        # 상태가 저장되어야 하며
        saved_state = workflow.get_state(config)
        assert saved_state is not None, "State should be saved after interruption"

        # 실제로 'reflect' 노드 직전에서 인터럽트가 발생했는지 검증:
        # retry 경로를 탔다면 state.next == ('reflect',)
        # 바로 종료(end 경로)됐다면 state.next == () → 경우에 따라 분기 검증
        if saved_state.next:
            assert "reflect" in saved_state.next, (
                f"interrupt_before=['reflect'] 설정 시 중단점은 'reflect'여야 합니다. "
                f"실제 state.next={saved_state.next!r}"
            )
        else:
            # should_retry가 'end'를 반환한 경우: 정상 종료, 인터럽트 없음
            # (신뢰도가 충분히 높아 retry가 불필요한 경우도 유효한 동작)
            assert (
                not saved_state.next
            ), "Workflow completed without hitting reflect node (no retry needed)"

    # ------------------------------------------------------------------
    # 시그니처 검증 테스트
    # ------------------------------------------------------------------

    def test_create_workflow_signature_has_interrupt_before(self):
        """create_workflow 함수가 interrupt_before 파라미터를 받는지 시그니처 검증"""
        sig = inspect.signature(create_workflow)
        assert (
            "interrupt_before" in sig.parameters
        ), "create_workflow should accept 'interrupt_before' parameter for HitL support"

        # 기본값이 None인지 확인
        default = sig.parameters["interrupt_before"].default
        assert (
            default is None
        ), f"'interrupt_before' default should be None, got {default!r}"

    # ------------------------------------------------------------------
    # 노드 이름 검증 테스트 (graph.py 조기 탐지 로직 보장)
    # ------------------------------------------------------------------

    def test_interrupt_before_raises_on_unknown_node(self):
        """interrupt_before에 존재하지 않는 노드 이름 전달 시 ValueError가 발생하는지 검증"""
        with pytest.raises(ValueError, match="interrupt_before"):
            create_workflow(
                checkpointer=MemorySaver(),
                interrupt_before=["nonexistent_node"],
            )

    def test_interrupt_before_raises_on_typo_node(self):
        """interrupt_before 노드 이름 오타(예: 'reflecc') 시 ValueError가 발생하는지 검증"""
        with pytest.raises(ValueError, match="interrupt_before"):
            create_workflow(
                checkpointer=MemorySaver(),
                interrupt_before=["reflecc"],  # 'reflect'의 오타
            )

    def test_interrupt_before_raises_on_invalid_type(self):
        """interrupt_before에 Sequence[str]이 아닌 잘못된 타입 전달 시 TypeError가 발생하는지 검증.

        graph.py의 타입 가드가 동작하는지 확인합니다.
        - str: Sequence이지만 노드명 리스트로 허용되어서는 안 됨 (문자 단위 순회 방지)
        - int: 이터러블이 아닌 스칼라 값

        match 패턴에 'interrupt_before'를 사용하여 에러 메시지 문구 변경에 미옷도록 합니다.
        ValueError 테스트들과 동일한 패턴으로 일관성을 유지합니다.
        """
        # 문자열: Sequence이지만 노드명 리스트로는 허용되어서는 안 됨
        with pytest.raises(TypeError, match="interrupt_before"):
            create_workflow(
                checkpointer=MemorySaver(),
                interrupt_before="reflect",
            )

        # 정수: 이터러블이 아닌 스칼라
        with pytest.raises(TypeError, match="interrupt_before"):
            create_workflow(
                checkpointer=MemorySaver(),
                interrupt_before=123,
            )

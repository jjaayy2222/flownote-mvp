from __future__ import annotations

from typing import Dict, Any, Optional, TYPE_CHECKING
from langgraph.graph import StateGraph, END

# Type Checking Only Imports
if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.checkpoint.base import BaseCheckpointSaver

from backend.agent.state import AgentState
from backend.agent.nodes import (
    analyze_node,
    retrieve_node,
    classify_node,
    validate_node,
    reflect_node,
    should_retry,
)
from backend.agent.checkpointer import get_checkpointer


def create_workflow(
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> CompiledStateGraph:
    """
    LangGraph 에이전트 워크플로우를 생성하고 컴파일합니다.

    Args:
        checkpointer (Optional[BaseCheckpointSaver]): 상태 저장을 위한 체크포인터.
                                                     None일 경우 get_checkpointer()를 통해 환경에 맞는 Saver를 자동 선택합니다.

    Returns:
        CompiledStateGraph: 실행 가능한 에이전트 객체 (Persistence 기능 포함)
    """
    # 1. StateGraph 생성
    workflow = StateGraph(AgentState)

    # 2. 노드 추가
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("classify", classify_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("reflect", reflect_node)

    # 3. 진입점 설정
    workflow.set_entry_point("analyze")

    # 4. 엣지 연결 (순차 실행)
    workflow.add_edge("analyze", "retrieve")
    workflow.add_edge("retrieve", "classify")
    workflow.add_edge("classify", "validate")

    # 5. 조건부 엣지 추가 (재시도 로직)
    workflow.add_conditional_edges(
        "validate", should_retry, {"end": END, "retry": "reflect"}
    )

    # 6. 재시도 루프 연결
    workflow.add_edge("reflect", "classify")

    # 7. 체크포인터 확보 (Persistence)
    if checkpointer is None:
        checkpointer = get_checkpointer()

    # 8. Human-in-the-Loop 설정 (Optional)
    interrupt_before = []

    # 9. 그래프 컴파일
    compiled_workflow = workflow.compile(
        checkpointer=checkpointer, interrupt_before=interrupt_before
    )

    return compiled_workflow

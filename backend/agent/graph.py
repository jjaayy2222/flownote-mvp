from typing import Dict, Any
from langgraph.graph import StateGraph, END

# Import CompiledStateGraph for type hinting
try:
    from langgraph.graph.state import CompiledStateGraph
except ImportError:
    # Fallback/Dummy if version structure differs (though likely present in installed version)
    from typing import Any as CompiledStateGraph

from backend.agent.state import AgentState
from backend.agent.nodes import (
    analyze_node,
    retrieve_node,
    classify_node,
    validate_node,
    reflect_node,
    should_retry,
)


def create_workflow() -> CompiledStateGraph:
    """
    LangGraph 에이전트 워크플로우를 생성하고 컴파일합니다.

    Returns:
        CompiledStateGraph: 실행 가능한 에이전트 객체
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

    # 7. 그래프 컴파일
    return workflow.compile()

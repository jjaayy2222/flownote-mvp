from __future__ import annotations

from collections.abc import (
    Sequence,
)  # isinstance 체크용: typing.Sequence는 런타임 체크 불가 (Python 3.9+)
from typing import Optional, TYPE_CHECKING
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
    interrupt_before: Sequence[str] | None = None,
) -> CompiledStateGraph:
    """
    LangGraph 에이전트 워크플로우를 생성하고 컴파일합니다.

    Args:
        checkpointer (Optional[BaseCheckpointSaver]): 상태 저장을 위한 체크포인터.
            None일 경우 get_checkpointer()를 통해 환경에 맞는 Saver를 자동 선택합니다.
        interrupt_before (Sequence[str] | None): Human-in-the-Loop를 위해 실행 전 중단할
            노드 이름 목록. 예: ["reflect"] - validate 후 reflect 진입 전 사용자 개입 허용.
            list, tuple 등 Sequence[str] 타입을 허용합니다.
            None 또는 빈 시퀀스이면 중단 없이 자동 실행됩니다.

    Returns:
        CompiledStateGraph: 실행 가능한 에이전트 객체 (Persistence + HitL 기능 포함)
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

    # 8. Human-in-the-Loop 설정
    # - list, tuple 등 collections.abc.Sequence 구현체는 모두 허용
    # - str/bytes: Sequence이지만 노드명 리스트 의도가 아님 → 문자/바이트 단위 순회 방지
    # - set, dict, generator 등 비시퀀스 이터러블: Sequence 계약 불만족 → TypeError
    # - int, bool 등 비이터러블 스칼라: Sequence 아님 → TypeError
    # - None은 빈 리스트로 정규화하여 중단 없이 자동 실행
    if interrupt_before is not None:
        if not isinstance(interrupt_before, Sequence) or isinstance(
            interrupt_before, (str, bytes)
        ):
            raise TypeError(
                "interrupt_before는 Sequence[str] 또는 None이어야 합니다. "
                f"전달된 타입: {type(interrupt_before).__name__!r}"
            )
    _interrupt_before: list[str] = (
        list(interrupt_before) if interrupt_before is not None else []
    )

    # 요소 타입 검증: 모든 요소가 str인지 확인 (list[int] 등 혼합 타입 조기 차단)
    if _interrupt_before:
        non_str_elements = [n for n in _interrupt_before if not isinstance(n, str)]
        if non_str_elements:
            raise TypeError(
                f"interrupt_before의 모든 요소는 str이어야 합니다. "
                f"잘못된 요소: {non_str_elements!r}"
            )

    # 전달된 노드 이름이 실제 그래프 노드 집합에 포함되는지 조기 검증
    # 오타나 잘못된 노드 이름을 컴파일 전에 탐지하여 런타임 오류를 방지
    if _interrupt_before:
        valid_nodes = set(workflow.nodes.keys())
        unknown_nodes = [n for n in _interrupt_before if n not in valid_nodes]
        if unknown_nodes:
            raise ValueError(
                f"interrupt_before에 알 수 없는 노드 이름이 포함되어 있습니다: {unknown_nodes}. "
                f"사용 가능한 노드: {sorted(valid_nodes)}"
            )

    # 9. 그래프 컴파일
    compiled_workflow = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=_interrupt_before,
    )

    return compiled_workflow

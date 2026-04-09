# backend/agent/chat/graph.py

from typing import Optional, Any
from langgraph.graph import StateGraph, END, START
# TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

from backend.agent.chat.state import AgentState
from backend.agent.chat.nodes import router_edge, standard_rag_node, fallback_search_node, responder_node
from backend.agent.checkpointer import get_checkpointer


def create_chat_workflow(checkpointer: Optional["BaseCheckpointSaver"] = None) -> "CompiledStateGraph":
    """
    채팅 에이전트(Multi-Agent) 워크플로우를 구성하고 컴파일합니다.
    기존의 RAG 검색과 일상 대화를 분기하는 시작점 역할을 합니다.
    
    Returns:
        CompiledStateGraph: 실행 가능한 채팅 그래프 객체
    """
    # 1. 상태(State) 스키마를 가진 그래프 초기화
    workflow = StateGraph(AgentState)
    
    # 2. 노드(Nodes) 추가
    # 각 노드는 AgentState를 입력받아, 변동될 속성의 딕셔너리를 반환합니다.
    workflow.add_node("standard_rag", standard_rag_node)
    workflow.add_node("fallback_search", fallback_search_node)
    workflow.add_node("responder", responder_node)
    
    # 3. 라우팅 (조건부 진입점)
    # 시작점(START)에서 사용자의 메시지를 받아, 조건부 엣지(router_edge)를 통해 
    # 검색 방식(standard_rag, fallback_search)을 선택하거나 단순 인사말인 responder로 직행할지 결정합니다.
    workflow.add_conditional_edges(
        START,
        router_edge,
        {
            "standard_rag": "standard_rag",
            "fallback_search": "fallback_search",
            "responder": "responder"
        }
    )
    
    # 4. 방향 엣지(Edges) 연결
    # 검색 작업(내부 문서 검색 혹은 타빌리 웹 검색)이 끝나면 무조건 Responder로 넘어와서 최종 텍스트 답변을 구성합니다.
    workflow.add_edge("standard_rag", "responder")
    workflow.add_edge("fallback_search", "responder")
    
    # Responder가 최종 응답을 생성하면 에이전트 그래프 모방을 종료(END)합니다.
    workflow.add_edge("responder", END)
    
    # 5. 체크포인터 확보 (메모리 및 세션 유지를 위함)
    if checkpointer is None:
        checkpointer = get_checkpointer()
        
    # 6. 컴파일 (실행 준비)
    compiled_workflow = workflow.compile(
        checkpointer=checkpointer
    )
    
    return compiled_workflow

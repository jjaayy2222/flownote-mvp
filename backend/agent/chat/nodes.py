# backend/agent/chat/nodes.py

import logging
from typing import Dict, Any, Literal
from langchain_core.messages import AIMessage

from backend.agent.chat.state import AgentState

logger = logging.getLogger(__name__)

def router_edge(state: AgentState) -> Literal["planner", "responder"]:
    """
    조건부 엣지(Conditional Edge):
    마지막 사용자 메시지의 의도를 간단히 파악하여 복잡한 추론/검색이 필요한지(planner),
    아니면 단순 인사말/단답형인지 판별하여 다음 노드로 라우팅합니다.
    """
    messages = state.get("messages", [])
    if not messages:
        return "responder"
        
    last_message = messages[-1]
    query = last_message.content if hasattr(last_message, "content") else str(last_message)
    
    # [임시 휴리스틱 모델링]
    # 실제 환경에서는 소형 LLM(분류기)이나 정규식, Intent 판단 모델이 들어갑니다.
    # 현재는 단순 인사말 등은 응답자(responder)로 직행하고, 그 외 질문은 계획자(planner)를 거친다고 가정합니다.
    simple_greetings = ["안녕", "hello", "hi", "반가워", "누구야"]
    # 쿼리의 길이가 짧고 인사말이 포함되어 있으면 단순 채팅 모드로 간주
    if len(query) < 15 and any(greet in query.lower() for greet in simple_greetings):
        logger.info("[Router] 질문 의도: 단순 대화 (-> responder)")
        return "responder"
        
    logger.info("[Router] 질문 의도: 검색/추론 도구 필요 (-> planner)")
    return "planner"


def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    계획자(Planner) 노드:
    - 외부 도구(Tool) 호출 및 복잡한 추론을 담당합니다.
    - 예: HybridSearchService를 호출하여 관련 문서(RAG)를 찾아냅니다.
    """
    logger.info("[Planner Node] 실행 중... (도구 호출 및 검색 활용 계획)")
    
    # 추후 'tools.py' 파트에서 RAG 검색 도구를 구현하고 여기서 호출 결과를 search_context 에 담을 예정입니다.
    # 지금은 기초 뼈대(Scaffolding)만 잡아둡니다.
    mock_context = "검색된 임시 컨텍스트 조각입니다 (Scaffolding Data)."
    
    return {
        "search_context": mock_context,
        "next_step": "responder" # Planner가 끝나면 최종 응답을 위해 responder로 이동
    }


def responder_node(state: AgentState) -> Dict[str, Any]:
    """
    응답 생성자(Responder) 노드:
    - 최종적으로 사용자에게 전달될 메시지를 스트리밍하거나 반환하기 전 조립합니다.
    - 대화 이력(messages)과 Planner가 획득한 context를 융합하여 LLM을 호출합니다.
    """
    logger.info("[Responder Node] 실행 중... (최종 응답 생성)")
    
    # TODO: ChatService.stream_chat의 로직을 향후 이 노드로 통합하여 SSE 스트리밍 연동
    mock_response = "임시 뼈대 단계에서의 시스템 AI 응답입니다."
    
    # 기존 메시지에 AI 답변을 누적시키기 위해 리스트로 반환 (Annotated[operator.add]에 의해 기존 배열에 병합됨)
    return {
        "messages": [AIMessage(content=mock_response)],
        "final_answer": mock_response
    }

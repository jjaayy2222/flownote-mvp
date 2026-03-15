# backend/agent/chat/nodes.py

import re
import logging
from typing import Dict, Any, Literal
from langchain_core.messages import AIMessage

from backend.agent.chat.state import AgentState

logger = logging.getLogger(__name__)

# 라우팅 휴리스틱을 위한 상수 (상단 분리 및 하드코딩 제거)
_SIMPLE_KOREAN_GREETINGS = ["안녕", "반가워", "누구야"]
_KOREAN_SUFFIXES = ["", "하세요", "하십니까", "해", "해요", "요", "히", "하신가요"]
_SIMPLE_LATIN_GREETINGS = ["hello", "hi"]

# 단순 인사말로 취급할 최대 쿼리 길이
_MAX_GREETING_LENGTH = 15

# 모듈 로드 시 허용되는 모든 한글 인사말 조합을 생성하여 탐색 복잡도 단축(O(1)) 및 합성어 오탐 완전 차단
_KOREAN_GREETING_FORMS = {
    base + suffix
    for base in _SIMPLE_KOREAN_GREETINGS
    for suffix in _KOREAN_SUFFIXES
}

# 라틴 인사말은 단어 단위 소문자 매칭을 위해 Set 구조화
_LATIN_GREETING_SET = set(_SIMPLE_LATIN_GREETINGS)

def _is_simple_greeting(cleaned_query: str) -> bool:
    """
    공백 기준으로 토큰화하여 단순 인사말인지 판별하는 헬퍼 함수
    정규식 조립의 복잡도를 낮추고 토큰 비교를 통해 경계 매칭을 완벽하게 구현합니다.
    """
    # 라틴 인사말 패턴 통일을 위해 영문은 소문자로 정규화 (한글에는 영향 없음)
    cleaned_query = cleaned_query.lower()
    
    tokens = cleaned_query.split()
    if not tokens:
        return False
        
    # 한글 인사말: 허용된 완전 형태(base + suffix)와의 정확한 토큰 매칭
    if any(token in _KOREAN_GREETING_FORMS for token in tokens):
        return True
        
    # 라틴 인사말: 단어 단위 일치 매칭 (e.g. "hi", "hello")
    if any(token in _LATIN_GREETING_SET for token in tokens):
        return True
        
    return False

def router_edge(state: AgentState) -> Literal["planner", "responder"]:
    """
    조건부 엣지(Conditional Edge):
    가장 마지막 사용자(Human) 메시지의 의도를 파악하여 
    복잡한 추론/검색이 필요한지(planner), 단순 인사말인지(responder) 판별합니다.
    """
    messages = state.get("messages", [])
    if not messages:
        logger.debug("[Router] 메시지가 없어 responder로 라우팅")
        return "responder"
        
    # 사용자의 마지막 메시지 탐색 (이전 AI 응답에 영향을 받지 않기 위함)
    user_query = ""
    for msg in reversed(messages):
        # LangChain BaseMessage type 속성 확인 (방어적 코딩)
        if hasattr(msg, "type") and msg.type == "human":
            user_query = msg.content if hasattr(msg, "content") else str(msg)
            break
            
    if not user_query:
        logger.debug("[Router] 사용자 메시지를 찾을 수 없어 responder로 라우팅")
        return "responder"
        
    # [임시 휴리스틱 모델링]
    # 실제 환경에서는 소형 LLM(분류기)이나 정규식, Intent 판단 모델이 들어갑니다.
    # 안전한 문자열 처리 및 소문자 변환
    user_query_str = str(user_query).strip().lower()
    
    # 기본적인 구두점 제거 및 공백 정규화 (오탐률 최소화 및 안정성 확보)
    cleaned_query = re.sub(r"[^\w가-힣\s]", " ", user_query_str)
    cleaned_query = re.sub(r"\s+", " ", cleaned_query).strip()

    # 토큰화 기반의 헬퍼 함수를 통해 인사말 여부 판별
    is_simple_greeting = _is_simple_greeting(cleaned_query)
    
    # 쿼리의 길이가 짧고 인사말로 판단되면 단순 채팅 모드로 간주
    if len(cleaned_query) < _MAX_GREETING_LENGTH and is_simple_greeting:
        # 민감 정보(PII) 마스킹 관점과 구조화된 로깅 지침 준수
        logger.info("[Router] 단순 대화 감지 -> responder", extra={"query_length": len(cleaned_query)})
        return "responder"
        
    logger.info("[Router] 검색/추론 도구 필요 판단 -> planner", extra={"query_length": len(cleaned_query)})
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
    
    # 그래프 라우팅은 graph.py에서 명시적인 엣지를 통해 제어되므로 next_step 상태는 반환하지 않습니다.
    return {
        "search_context": mock_context,
    }


def responder_node(state: AgentState) -> Dict[str, Any]:
    """
    응답 생성자(Responder) 노드:
    - 최종적으로 사용자에게 전달될 메시지를 스트리밍하거나 반환하기 전 조립합니다.
    - 대화 이력(messages)과 Planner가 획득한 context를 융합하여 LLM을 호출합니다.
    """
    logger.info("[Responder Node] 실행 중... (최종 응답 생성)")
    
    # NotRequired 필드에 대한 안전한 접근 (.get 사용 필수)
    # Planner에서 넘어온 문맥 정보가 없다면 빈 문자열로 처리
    context = state.get("search_context", "")
    
    # 구조화된 로깅을 활용해 내부 컨텍스트 길이를 트레이싱 (UI 노출 방지 및 Dead Code 해소)
    if context:
        logger.info("[Responder Node] 문맥 정보 활용", extra={"context_length": len(context)})
    
    # TODO: ChatService.stream_chat의 로직을 향후 이 노드로 통합하여 SSE 스트리밍 연동
    mock_response = "임시 뼈대 단계에서의 시스템 AI 응답입니다."
    
    # 기존 메시지에 AI 답변을 누적시키기 위해 리스트로 반환 (Annotated[operator.add]에 의해 기존 배열에 병합됨)
    return {
        "messages": [AIMessage(content=mock_response)],
        "final_answer": mock_response
    }

# backend/agent/chat/nodes.py

import re
import logging
from typing import Dict, Any, Literal, cast
from langchain_core.messages import AIMessage, SystemMessage, BaseMessage

from backend.agent.chat.state import AgentState
from backend.agent.chat.tools import search_documents_tool
from backend.services.chat_service import get_chat_service

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
    # 불필요한 토큰화 연산을 방지하기 위한 조기 반환(Early Return) 패턴 및 길이 캡슐화
    if len(cleaned_query) >= _MAX_GREETING_LENGTH:
        return False

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
        # cast()로 타입 체커에 BaseMessage임을 명시하여 .type/.content 속성 접근 허용
        if hasattr(msg, "type") and hasattr(msg, "content"):
            typed_msg = cast(BaseMessage, msg)
            if typed_msg.type == "human":
                user_query = str(typed_msg.content)
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

    # 토큰화 기반의 헬퍼 함수를 통해 캡슐화된 인사말/길이 검증 및 여부 판별
    is_simple_greeting = _is_simple_greeting(cleaned_query)
    
    # 로그 메타데이터 중복 방지를 위한 공통 속성 딕셔너리 분리
    router_log_extra: Dict[str, Any] = {
        "cleaned_query_length": len(cleaned_query),
        "max_greeting_length": _MAX_GREETING_LENGTH
    }
    
    # 인사말 판별기(내부 길이 제한 등 로직 포함)를 통과하면 응답자 모드로 직행
    if is_simple_greeting:
        # 민감 정보(PII) 마스킹 관점과 구조화된 로깅 지침 준수
        router_log_extra["target"] = "responder"
        logger.info("[Router] 단순 대화 감지 -> responder", extra=router_log_extra)
        return "responder"
        
    router_log_extra["target"] = "planner"
    logger.info("[Router] 검색/추론 도구 필요 판단 -> planner", extra=router_log_extra)
    return "planner"


async def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    계획자(Planner) 노드:
    - 외부 도구(Tool) 호출 및 복잡한 추론을 담당합니다.
    - 질문의 의도를 분석하고 필요한 도구를 LLM이 스스로 결정합니다.
    """
    logger.info("[Planner Node] 실행 중... (도구 호출 및 검색 활용 계획)")
    
    messages = state.get("messages", [])
    if not messages:
        return {"search_context": ""}
        
    chat_svc = get_chat_service()
    llm = chat_svc._get_llm(streaming=False)
    
    # 🌟 에이전트가 사용할 수 있도록 검색 도구 바인딩 (Tool Wrapping)
    tools = [search_documents_tool]
    llm_with_tools = llm.bind_tools(tools)
    
    # Planner 시스템 프롬프트 (질문 의도를 파악하고 도구를 쓸지 결정)
    sys_prompt = SystemMessage(
        content="당신은 사용자의 질문을 분석하고 외부 지식이 필요한 경우 적절한 도구를 실행하여 정보를 수집하는 Planner입니다.\n"
                "질문에 답하기 위해 프로젝트 내부 문서, 규정, 특정 지식 확인이 필요하다면 즉시 'search_documents_tool'을 호출하세요.\n"
                "단순 안부 이외의 대부분의 사실 확인은 이 도구를 통해 컨텍스트를 얻는 것이 안전합니다."
    )
    
    plan_messages = [sys_prompt] + messages
    # 명시적 str 누산기 사용 (Pyre2의 AugAssign 타입 추론 오류 방지)
    _ctx_base: str = str(state.get("search_context", "") or "")
    ctx_parts: list[str] = [_ctx_base] if _ctx_base else []
    
    try:
        response = await llm_with_tools.ainvoke(plan_messages)
        
        # cast()로 AIMessage 타입 명시 → .tool_calls 속성 접근 허용 (Pyre2 타입 에러 해소)
        typed_plan_response = cast(AIMessage, response)
        # LLM이 도구 호출(ToolCall)을 결정했는지 판별
        if hasattr(typed_plan_response, "tool_calls") and typed_plan_response.tool_calls:
            logger.info(f"[Planner Node] LLM이 {len(response.tool_calls)}개의 도구 호출을 결정했습니다.")
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                if tool_name == "search_documents_tool":
                    query_arg = str(tool_args.get("query", ""))
                    logger.info(f"[Planner Node] -> search_documents_tool 호출 요청 (query: {query_arg})")
                    
                    # 🚀 도구 실행 (비동기) — list 누산으로 타입 안정성 확보
                    tool_res = str(await search_documents_tool.ainvoke(tool_args))
                    ctx_parts.append(f"\n[검색 도구 호출 결과 (쿼리: {query_arg})]\n{tool_res}\n")
        else:
            logger.info("[Planner Node] LLM이 별도의 도구 호출 없이 자체 판단 가능으로 결론내렸습니다.")
            if not ctx_parts:
                ctx_parts.append("검색 도구 없이 자체 지식으로 답변을 구성하거나 일반적인 답변을 합니다.")
                
    except Exception as e:
        logger.error(f"[Planner Node] LLM 추론 중 에러 발생 (Fallback 동작): {str(e)}")
        # ⚠️ 무한 루프 및 예외에 대한 안전장치(Fallback) 처리
        ctx_parts.append("\n[System] Planner 처리 중 LLM 오류가 발생해 자동 도구 검색을 완료할 수 없었습니다. 일반 지식과 현재 문맥을 바탕으로 답변해주세요.")
        
    search_context: str = "".join(ctx_parts).strip()
    return {
        "search_context": search_context
    }


async def responder_node(state: AgentState) -> Dict[str, Any]:
    """
    응답 생성자(Responder) 노드:
    - 최종적으로 사용자에게 전달될 메시지를 반환합니다.
    - 대화 이력(messages)과 Planner가 획득한 context를 융합하여 LLM을 호출합니다.
    """
    logger.info("[Responder Node] 실행 중... (최종 응답 조립 및 생성)")
    
    # NotRequired 필드에 대한 안전한 접근
    context: str = str(state.get("search_context", "") or "")
    
    # 구조화된 로깅
    if context:
        logger.info("[Responder Node] 문맥(Context) 정보 확보 완료", extra={"context_length": len(context)})
    
    messages = state.get("messages", [])
    user_id = state.get("user_id", "default_user")
    
    chat_svc = get_chat_service()
    
    # 사용자 개인화 상황에 맞춘 시스템 프롬프트 작성 (Onboarding Context)
    user_context_msg = chat_svc._get_user_context_prompt_text(user_id)
    
    system_template = f"""{user_context_msg}

Answer the user's question clearly and accurately, summarizing the information logically.
If you are provided with context below, use ONLY the provided context to answer. 
If the given context does not contain the answer, politely state that you cannot find the answer in the provided internal documents, and then answer cautiously based on your general knowledge.
Do not mention the words "context" or "provided text" explicitly to the user.
If you used any document from the context, YOU MUST use inline citations in the format [1], [2] at the end of the sentence.

Context: 
{context}
"""
    
    # TODO: ChatService.stream_chat의 스트리밍 통합 전까지는 완성 텍스트 반환 처리
    llm = chat_svc._get_llm(streaming=False) 
    
    # 시스템 프롬프트 조립
    sys_msg = SystemMessage(content=system_template)
    final_messages = [sys_msg] + messages
    
    try:
        response = await llm.ainvoke(final_messages)
        # cast()로 AIMessage 타입 명시 → .content 속성 접근 허용 (Pyre2 타입 에러 해소)
        typed_response = cast(AIMessage, response)
        final_answer: str = str(typed_response.content) if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.error(f"[Responder Node] LLM 응답 실패 (Fallback 동작): {str(e)}")
        # ⚠️ 안전장치(Fallback) 적용
        final_answer = ("죄송합니다, 현재 트래픽이 많거나 응답 생성 중에 내부적인 통신 오류가 발생했습니다. "
                        "잠시 후 다시 시도해 주시기 바랍니다.")
    
    # 기존 메시지에 이번 에이전트의 AI 답변을 추가시켜 전달
    return {
        "messages": [AIMessage(content=final_answer)],
        "final_answer": final_answer
    }

# backend/agent/chat/nodes.py

import re
import logging
from typing import Dict, Any, Literal, cast
from langchain_core.messages import AIMessage, SystemMessage, BaseMessage

from backend.agent.chat.state import AgentState
from backend.agent.chat.tools import search_documents_tool
from backend.services.chat_service import get_chat_service

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 라우팅 휴리스틱 상수 (하드코딩 제거, 상단 분리)
# ─────────────────────────────────────────────────────────────────────────────
_SIMPLE_KOREAN_GREETINGS = ["안녕", "반가워", "누구야"]
_KOREAN_SUFFIXES = ["", "하세요", "하십니까", "해", "해요", "요", "히", "하신가요"]
_SIMPLE_LATIN_GREETINGS = ["hello", "hi"]
_MAX_GREETING_LENGTH = 15

# search_context 최대 길이 제한: 도구 출력 합산이 프롬프트 토큰 예산을 초과하지 않도록 보호
# [Engineering Decision] 검색 결과 총합을 8,000자로 제한하여 LLM 컨텍스트 윈도우 안전 범위 유지
_MAX_SEARCH_CONTEXT_CHARS = 8_000

# 모듈 로드 시 허용되는 모든 한글 인사말 조합을 생성 (O(1) 탐색 및 합성어 오탐 차단)
_KOREAN_GREETING_FORMS = {
    base + suffix
    for base in _SIMPLE_KOREAN_GREETINGS
    for suffix in _KOREAN_SUFFIXES
}
_LATIN_GREETING_SET = set(_SIMPLE_LATIN_GREETINGS)


def _is_simple_greeting(cleaned_query: str) -> bool:
    """
    공백 기준으로 토큰화하여 단순 인사말인지 판별하는 헬퍼 함수.
    정규식 조립의 복잡도를 낮추고 토큰 비교를 통해 경계 매칭을 완벽하게 구현합니다.
    """
    if len(cleaned_query) >= _MAX_GREETING_LENGTH:
        return False
    cleaned_query = cleaned_query.lower()
    tokens = cleaned_query.split()
    if not tokens:
        return False
    if any(token in _KOREAN_GREETING_FORMS for token in tokens):
        return True
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

    user_query = ""
    for msg in reversed(messages):
        # cast()로 타입 체커에 BaseMessage임을 명시하여 .type/.content 속성 접근 허용
        if hasattr(msg, "type") and hasattr(msg, "content"):
            typed_msg = cast(BaseMessage, msg)
            if typed_msg.type == "human":
                user_query = str(typed_msg.content)
                break

    if not user_query:
        logger.debug("[Router] 사용자 메시지를 찾을 수 없어 responder로 라우팅")
        return "responder"

    user_query_str = str(user_query).strip().lower()
    cleaned_query = re.sub(r"[^\w가-힣\s]", " ", user_query_str)
    cleaned_query = re.sub(r"\s+", " ", cleaned_query).strip()
    is_simple_greeting = _is_simple_greeting(cleaned_query)

    router_log_extra: Dict[str, Any] = {
        "cleaned_query_length": len(cleaned_query),
        "max_greeting_length": _MAX_GREETING_LENGTH
    }

    if is_simple_greeting:
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

    [Engineering Decision - Coupling]
    현재는 ChatService의 _get_llm을 통해 LLM을 획득하고 있습니다.
    향후 Phase 3 Integration 단계에서 LLM 제공자를 DI(의존성 주입)로 분리할 예정입니다.
    """
    logger.info("[Planner Node] 실행 중... (도구 호출 및 검색 활용 계획)")

    messages = state.get("messages", [])
    if not messages:
        return {"search_context": "", "planner_failed": False}

    chat_svc = get_chat_service()
    llm = chat_svc._get_llm(streaming=False)

    tools = [search_documents_tool]
    llm_with_tools = llm.bind_tools(tools)

    sys_prompt = SystemMessage(
        content="당신은 사용자의 질문을 분석하고 외부 지식이 필요한 경우 적절한 도구를 실행하여 정보를 수집하는 Planner입니다.\n"
                "질문에 답하기 위해 프로젝트 내부 문서, 규정, 특정 지식 확인이 필요하다면 즉시 'search_documents_tool'을 호출하세요.\n"
                "단순 안부 이외의 대부분의 사실 확인은 이 도구를 통해 컨텍스트를 얻는 것이 안전합니다."
    )

    plan_messages = [sys_prompt] + messages
    _ctx_base: str = str(state.get("search_context", "") or "")
    ctx_parts: list[str] = [_ctx_base] if _ctx_base else []

    # [Comment 1 반영] 플래너 실패 여부를 search_context와 완전히 분리하여 별도 상태로 관리
    planner_failed: bool = False
    planner_error_message: str = ""

    try:
        response = await llm_with_tools.ainvoke(plan_messages)
        typed_plan_response = cast(AIMessage, response)

        if hasattr(typed_plan_response, "tool_calls") and typed_plan_response.tool_calls:
            logger.info(
                "[Planner Node] LLM이 도구 호출을 결정했습니다.",
                extra={"tool_call_count": len(typed_plan_response.tool_calls)}
            )
            for tool_call in typed_plan_response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                if tool_name == "search_documents_tool":
                    query_arg = str(tool_args.get("query", ""))
                    logger.info(
                        "[Planner Node] -> search_documents_tool 호출",
                        extra={"query_length": len(query_arg)}  # PII 방지: 원문 대신 길이 로깅
                    )
                    tool_res = str(await search_documents_tool.ainvoke(tool_args))
                    ctx_parts.append(f"\n[검색 결과 (쿼리 길이: {len(query_arg)}자)]\n{tool_res}\n")
        else:
            logger.info("[Planner Node] LLM이 도구 없이 자체 판단 가능으로 결론내렸습니다.")
            if not ctx_parts:
                ctx_parts.append("검색 도구 없이 자체 지식으로 답변을 구성합니다.")

    except Exception as e:
        logger.error(
            "[Planner Node] LLM 추론 중 에러 발생",
            extra={"error_type": type(e).__name__}  # 에러 원문 대신 타입만 로깅 (보안)
        )
        # [Comment 1 반영] 에러 메시지를 search_context에 섞지 않고 별도 상태 필드로 분리
        planner_failed = True
        planner_error_message = "Planner 실행 중 오류가 발생했습니다. 검색 결과 없이 직접 응답을 시도합니다."

    # [전체 코멘트 반영] search_context 토큰 예산 초과 방지: 최대 길이 제한 적용
    raw_context: str = "".join(ctx_parts).strip()
    if len(raw_context) > _MAX_SEARCH_CONTEXT_CHARS:
        raw_context = raw_context[:_MAX_SEARCH_CONTEXT_CHARS] + "...(검색 결과가 길어 자동 잘림)"
        logger.warning(
            "[Planner Node] search_context가 최대 길이를 초과하여 잘렸습니다.",
            extra={"max_chars": _MAX_SEARCH_CONTEXT_CHARS}
        )

    return {
        "search_context": raw_context,
        "planner_failed": planner_failed,
        "planner_error_message": planner_error_message,
    }


async def responder_node(state: AgentState) -> Dict[str, Any]:
    """
    응답 생성자(Responder) 노드:
    - 최종적으로 사용자에게 전달될 메시지를 반환합니다.
    - 대화 이력(messages)과 Planner가 획득한 context를 융합하여 LLM을 호출합니다.

    [Engineering Decision - Coupling]
    현재는 ChatService의 _get_user_context_prompt_text를 통해 사용자 맥락을 획득합니다.
    향후 Phase 3 Integration 단계에서 퍼블릭 메서드로 노출 또는 DI로 분리할 예정입니다.
    """
    logger.info("[Responder Node] 실행 중... (최종 응답 조립 및 생성)")

    context: str = str(state.get("search_context", "") or "")
    planner_failed: bool = bool(state.get("planner_failed", False))
    planner_error_msg: str = str(state.get("planner_error_message", "") or "")

    if context:
        logger.info("[Responder Node] 문맥(Context) 정보 확보 완료", extra={"context_length": len(context)})

    # [Comment 1 반영] planner_failed 플래그로 폴백 여부 판단 (search_context 내 시스템 메시지 탐색 불필요)
    if planner_failed:
        logger.warning("[Responder Node] Planner 실패 감지. 검색 없이 일반 답변 시도.", extra={"reason": planner_error_msg})

    messages = state.get("messages", [])
    user_id: str = str(state.get("user_id", "default_user") or "default_user")

    chat_svc = get_chat_service()
    user_context_msg = chat_svc._get_user_context_prompt_text(user_id)

    # [Comment 2 반영] context 없을 때 'Context:' 블록 자체를 생략 (토큰 절약 + 지침 일관성 유지)
    context_block = ""
    if context:
        context_block = f"\n\nContext:\n{context}"

    system_template = f"""{user_context_msg}

Answer the user's question clearly and accurately, summarizing the information logically.
If you are provided with context below, use ONLY the provided context to answer.
If the given context does not contain the answer, politely state that you cannot find the answer in the provided internal documents, and then answer cautiously based on your general knowledge.
Do not mention the words "context" or "provided text" explicitly to the user.
If you used any document from the context, YOU MUST use inline citations in the format [1], [2] at the end of the sentence.{context_block}
"""

    llm = chat_svc._get_llm(streaming=False)
    sys_msg = SystemMessage(content=system_template)
    final_messages = [sys_msg] + messages

    try:
        response = await llm.ainvoke(final_messages)
        typed_response = cast(AIMessage, response)
        final_answer: str = str(typed_response.content) if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.error(
            "[Responder Node] LLM 응답 생성 실패",
            extra={"error_type": type(e).__name__}
        )
        final_answer = ("죄송합니다, 현재 트래픽이 많거나 응답 생성 중에 내부적인 통신 오류가 발생했습니다. "
                        "잠시 후 다시 시도해 주시기 바랍니다.")

    return {
        "messages": [AIMessage(content=final_answer)],
        "final_answer": final_answer
    }

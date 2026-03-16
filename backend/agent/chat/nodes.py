# backend/agent/chat/nodes.py

import re
import logging
from itertools import islice
from typing import Dict, Any, Literal, cast, List
from langchain_core.messages import AIMessage, SystemMessage, BaseMessage

from backend.agent.chat.state import AgentState
from backend.agent.chat.tools import search_documents_tool
from backend.services.chat_service import get_chat_service

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 모듈 상수 (하드코딩 완전 배제)
# ─────────────────────────────────────────────────────────────────────────────
_SIMPLE_KOREAN_GREETINGS = ["안녕", "반가워", "누구야"]
_KOREAN_SUFFIXES = ["", "하세요", "하십니까", "해", "해요", "요", "히", "하신가요"]
_SIMPLE_LATIN_GREETINGS = ["hello", "hi"]
_MAX_GREETING_LENGTH = 15

# [Engineering Decision] 검색 결과 총합 토큰 예산 보호 (LLM 컨텍스트 윈도우 안전 범위 유지)
# 명시적 int 타입 어노테이션 적용 → Pyre2가 Literal[8000]이아닌 int로 추론하도록 일치
_MAX_SEARCH_CONTEXT_CHARS: int = 8_000

# 모듈 로드 시 한글 인사말 조합 생성 (O(1) 탐색, 합성어 오탐 차단)
_KOREAN_GREETING_FORMS = {
    base + suffix for base in _SIMPLE_KOREAN_GREETINGS for suffix in _KOREAN_SUFFIXES
}
_LATIN_GREETING_SET = set(_SIMPLE_LATIN_GREETINGS)


# ─────────────────────────────────────────────────────────────────────────────
# 타입 정의 및 공통 헬퍼
# ─────────────────────────────────────────────────────────────────────────────


def _is_simple_greeting(cleaned_query: str) -> bool:
    """
    공백 기준으로 토큰화하여 단순 인사말인지 판별하는 헬퍼 함수.
    토큰 비교를 통해 경계 매칭을 완벽하게 구현하고 합성어 오탐을 방지합니다.
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


def _truncate_context(raw_context: str) -> str:
    """
    search_context가 LLM 토큰 예산을 초과하지 않도록 최대 길이로 잘라내는 헬퍼.
    """
    if len(raw_context) <= _MAX_SEARCH_CONTEXT_CHARS:
        return raw_context
    logger.warning(
        "[Context] search_context가 최대 길이를 초과하여 잘렸습니다.",
        extra={
            "max_chars": _MAX_SEARCH_CONTEXT_CHARS,
            "original_len": len(raw_context),
        },
    )
    # [Pyre2 Workaround] [:N] 슬라이스 대신 itertools.islice 사용.
    # Pyre2가 [:N]을 slice[int,int,int]로 고정 추론해 str/__getitem__ 시그니처와 불일치하는 버그 우회.
    # 런타임 동작은 [:_MAX_SEARCH_CONTEXT_CHARS]와 100% 동일.
    suffix = "...(검색 결과가 길어 자동 잘림)"
    head = "".join(islice(raw_context, _MAX_SEARCH_CONTEXT_CHARS))
    return head + suffix


async def _run_planner_with_tools(
    plan_messages: List[BaseMessage],
    base_context: str,
) -> Dict[str, Any]:
    """
    LLM에 도구 호출 권한을 부여하고, 도구를 실행하여 search_context를 반환하는 오케스트레이션 헬퍼.
    """
    chat_svc = get_chat_service()
    llm = chat_svc._get_llm(streaming=False)
    llm_with_tools = llm.bind_tools([search_documents_tool])

    ctx_parts: List[str] = [base_context] if base_context else []
    planner_failed = False
    planner_error_message = ""

    try:
        response = await llm_with_tools.ainvoke(plan_messages)
        typed_response = cast(AIMessage, response)

        if hasattr(typed_response, "tool_calls") and typed_response.tool_calls:
            logger.info(
                "[Planner] LLM이 도구 호출을 결정했습니다.",
                extra={"tool_call_count": len(typed_response.tool_calls)},
            )
            for tool_call in typed_response.tool_calls:
                tool_name = tool_call.get("name")
                raw_args = tool_call.get("args") or {}

                if not isinstance(raw_args, dict):
                    logger.warning(
                        "[Tool Dispatch] 예상치 못한 args 타입 무시",
                        extra={
                            "tool_name": tool_name,
                            "args_type": type(raw_args).__name__,
                        },
                    )
                    continue

                tool_args = raw_args

                if tool_name != "search_documents_tool":
                    logger.debug(
                        "[Tool Dispatch] 미지원 도구 요청 무시",
                        extra={"tool_name": tool_name},
                    )
                    continue

                query_arg = str(tool_args.get("query", ""))
                logger.info(
                    "[Planner] -> search_documents_tool 호출",
                    extra={"query_length": len(query_arg)},
                )
                tool_res = str(await search_documents_tool.ainvoke(tool_args))
                ctx_parts.append(
                    f"\n[검색 결과 (쿼리 길이: {len(query_arg)}자)]\n{tool_res}\n"
                )
        else:
            logger.info("[Planner] LLM이 도구 없이 자체 판단 가능으로 결론내렸습니다.")
    except Exception as e:
        # 광범위한 예외를 삼키더라도 발생 원인을 파악할 수 있도록 error_msg와 exc_info 기록
        logger.error(
            "[Planner] LLM 추론 중 에러 발생",
            extra={
                "error_type": type(e).__name__,
                "error_msg": str(e),
            },
            exc_info=True,
        )
        planner_failed = True
        planner_error_message = "Planner 실행 중 오류가 발생했습니다. 검색 결과 없이 직접 응답을 시도합니다."

    raw_context = _truncate_context("".join(ctx_parts).strip())
    return {
        "search_context": raw_context,
        "planner_failed": planner_failed,
        "planner_error_message": planner_error_message,
    }


def _build_responder_system_message(
    user_context_msg: str,
    context: str,
) -> SystemMessage:
    """
    Responder용 시스템 프롬프트를 조립하는 헬퍼.
    """
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
    return SystemMessage(content=system_template)


# ─────────────────────────────────────────────────────────────────────────────
# 노드 & 엣지 (Thin Orchestrators)
# ─────────────────────────────────────────────────────────────────────────────


def router_edge(state: AgentState) -> Literal["planner", "responder"]:
    """
    조건부 엣지(Conditional Edge):
    가장 마지막 Human 메시지의 의도를 파악하여
    복잡한 추론/검색이 필요한지(planner), 단순 인사말인지(responder) 판별합니다.
    """
    messages = state.get("messages", [])
    if not messages:
        logger.debug("[Router] 메시지가 없어 responder로 라우팅")
        return "responder"

    user_query = ""
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human" and hasattr(msg, "content"):
            user_query = str(cast(BaseMessage, msg).content)
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
        "max_greeting_length": _MAX_GREETING_LENGTH,
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
    계획자(Planner) 노드 — Thin Orchestrator:
    - 상태를 수집하고 헬퍼를 호출하여 도구 실행 및 컨텍스트를 구성한 후 반환합니다.

    [Engineering Decision - Coupling]
    현재 시스템 내에서 LLM 결합 방식에 대한 의존성이 존재하며,
    Phase 3 Integration 단계에서 LLM 제공자를 DI(의존성 주입)로 분리할 예정입니다.
    """
    logger.info("[Planner Node] 실행 중... (도구 호출 및 검색 활용 계획)")

    messages = state.get("messages", [])
    if not messages:
        return {
            "search_context": "",
            "planner_failed": False,
            "planner_error_message": "",
        }

    base_context = str(state.get("search_context", "") or "")

    sys_prompt = SystemMessage(
        content=(
            "당신은 사용자의 질문을 분석하고 외부 지식이 필요한 경우 적절한 도구를 실행하여 정보를 수집하는 Planner입니다.\n"
            "질문에 답하기 위해 프로젝트 내부 문서, 규정, 특정 지식 확인이 필요하다면 즉시 'search_documents_tool'을 호출하세요.\n"
            "단순 안부 이외의 대부분의 사실 확인은 이 도구를 통해 컨텍스트를 얻는 것이 안전합니다."
        )
    )
    plan_messages = [sys_prompt] + messages

    return await _run_planner_with_tools(plan_messages, base_context)


async def responder_node(state: AgentState) -> Dict[str, Any]:
    """
    응답 생성자(Responder) 노드 — Thin Orchestrator:
    - Planner가 수집한 context와 대화 이력을 융합하여 최종 응답을 생성합니다.

    [Engineering Decision - Coupling]
    현재 ChatService._get_user_context_prompt_text를 통해 사용자 맥락을 획득합니다.
    Phase 3 Integration 단계에서 퍼블릭 메서드 노출 또는 DI로 분리할 예정입니다.
    """
    logger.info("[Responder Node] 실행 중... (최종 응답 조립 및 생성)")

    context: str = str(state.get("search_context", "") or "")
    planner_failed: bool = bool(state.get("planner_failed", False))
    planner_error_msg: str = str(state.get("planner_error_message", "") or "")

    if context:
        logger.info(
            "[Responder Node] 문맥(Context) 정보 확보 완료",
            extra={"context_length": len(context)},
        )
    if planner_failed:
        logger.warning(
            "[Responder Node] Planner 실패 감지. 검색 없이 일반 답변 시도.",
            extra={"reason": planner_error_msg},
        )

    messages = state.get("messages", [])
    user_id: str = str(state.get("user_id", "default_user") or "default_user")

    chat_svc = get_chat_service()
    user_context_msg = chat_svc._get_user_context_prompt_text(user_id)
    sys_msg = _build_responder_system_message(user_context_msg, context)

    llm = chat_svc._get_llm(streaming=False)
    final_messages = [sys_msg] + messages

    try:
        response = await llm.ainvoke(final_messages)
        typed_response = cast(AIMessage, response)
        final_answer: str = (
            str(typed_response.content)
            if hasattr(response, "content")
            else str(response)
        )
    except Exception as e:
        logger.error(
            "[Responder Node] LLM 응답 생성 실패",
            extra={
                "error_type": type(e).__name__,
                "error_msg": str(e),
            },
            exc_info=True,
        )
        final_answer = (
            "죄송합니다, 현재 트래픽이 많거나 응답 생성 중에 내부적인 통신 오류가 발생했습니다. "
            "잠시 후 다시 시도해 주시기 바랍니다."
        )

    return {
        "messages": [AIMessage(content=final_answer)],
        "final_answer": final_answer,
    }

# backend/agent/chat/nodes.py

import re
import logging
from itertools import islice
from typing import Dict, Any, Literal, cast, List, Tuple
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
# 헬퍼 함수 (관심사 분리 / Comment 5 반영)
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


def _get_last_human_content(messages: List[BaseMessage]) -> str:
    """
    메시지 목록에서 가장 마지막 Human 메시지의 내용을 반환하는 헬퍼.
    메시지가 없거나 Human 메시지가 없으면 빈 문자열 반환.
    [Comment 5 반영] router_edge의 방어적 루프를 헬퍼로 추출하여 라우터를 명확하게 유지.
    """
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human" and hasattr(msg, "content"):
            return str(cast(BaseMessage, msg).content)
    return ""


def _truncate_context(raw_context: str) -> str:
    """
    search_context가 LLM 토큰 예산을 초과하지 않도록 최대 길이로 잘라내는 헬퍼.
    [Comment 5 반영] 잘라내기 로직을 planner_node에서 분리하여 재사용성 확보.
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


async def _execute_tool_call(tool_call: Dict[str, Any], ctx_parts: List[str]) -> None:
    """
    단일 도구 호출을 실행하고 결과를 ctx_parts에 누산하는 헬퍼.
    [Comment 5 반영] planner_node에서 도구 디스패치 루프를 분리.
    미지원 도구는 조용히 무시하여 향후 추가 도구 확장에 열린 구조 유지.
    """
    tool_name = tool_call["name"]
    tool_args = tool_call["args"]

    if tool_name != "search_documents_tool":
        logger.debug(
            "[Tool Dispatch] 미지원 도구 요청 무시", extra={"tool_name": tool_name}
        )
        return

    query_arg = str(tool_args.get("query", ""))
    # [PII 보호] query 원문이 아닌 길이(비민감 메타데이터)만 로깅
    logger.info(
        "[Planner] -> search_documents_tool 호출",
        extra={"query_length": len(query_arg)},
    )
    tool_res = str(await search_documents_tool.ainvoke(tool_args))
    ctx_parts.append(f"\n[검색 결과 (쿼리 길이: {len(query_arg)}자)]\n{tool_res}\n")


async def _run_planner_with_tools(
    plan_messages: List[BaseMessage], base_context: str
) -> Tuple[str, bool, str]:
    """
    LLM에 도구 호출 권한을 부여하고, 도구를 실행하여 search_context를 반환하는 핵심 헬퍼.
    [Comment 5 반영] planner_node의 핵심 로직을 분리하여 planner_node를 thin orchestrator로 유지.

    Returns:
        (search_context, planner_failed, planner_error_message)
    """
    chat_svc = get_chat_service()
    llm = chat_svc._get_llm(streaming=False)
    llm_with_tools = llm.bind_tools([search_documents_tool])

    ctx_parts: List[str] = [base_context] if base_context else []
    planner_failed: bool = False
    planner_error_message: str = ""

    try:
        response = await llm_with_tools.ainvoke(plan_messages)
        typed_response = cast(AIMessage, response)

        if hasattr(typed_response, "tool_calls") and typed_response.tool_calls:
            logger.info(
                "[Planner] LLM이 도구 호출을 결정했습니다.",
                extra={"tool_call_count": len(typed_response.tool_calls)},
            )
            for tool_call in typed_response.tool_calls:
                await _execute_tool_call(tool_call, ctx_parts)
        else:
            # [Overall Comment 2 / Comment 3 반영]
            # 도구 미사용 시 placeholder 문구를 search_context에 삽입하지 않음.
            # "ONLY the provided context" 지침과의 충돌 방지 + 플래그로만 상태 관리.
            logger.info("[Planner] LLM이 도구 없이 자체 판단 가능으로 결론내렸습니다.")

    except Exception as e:
        # [보안] 예외 상세 내용은 로그에만 기록, planner_error_message는 고정 메시지로 관리
        logger.error(
            "[Planner] LLM 추론 중 에러 발생", extra={"error_type": type(e).__name__}
        )
        planner_failed = True
        planner_error_message = "Planner 실행 중 오류가 발생했습니다. 검색 결과 없이 직접 응답을 시도합니다."

    raw_context = _truncate_context("".join(ctx_parts).strip())
    return raw_context, planner_failed, planner_error_message


def _build_planner_messages(state: AgentState) -> List[BaseMessage]:
    """
    Planner용 시스템 프롬프트와 대화 메시지를 조립하는 헬퍼.
    [Comment 5 반영] 프롬프트 조립 관심사를 분리하여 테스트 및 수정 용이성 확보.
    """
    messages = state.get("messages", [])
    sys_prompt = SystemMessage(
        content=(
            "당신은 사용자의 질문을 분석하고 외부 지식이 필요한 경우 적절한 도구를 실행하여 정보를 수집하는 Planner입니다.\n"
            "질문에 답하기 위해 프로젝트 내부 문서, 규정, 특정 지식 확인이 필요하다면 즉시 'search_documents_tool'을 호출하세요.\n"
            "단순 안부 이외의 대부분의 사실 확인은 이 도구를 통해 컨텍스트를 얻는 것이 안전합니다."
        )
    )
    return [sys_prompt] + messages


def _build_responder_system_message(
    user_context_msg: str, context: str
) -> SystemMessage:
    """
    Responder용 시스템 프롬프트를 조립하는 헬퍼.
    [Comment 5 반영] 프롬프트 조립 관심사를 분리.
    [Comment 2 반영] context가 없을 때 'Context:' 블록 자체를 생략하여 불필요한 토큰 낭비와
    지침("ONLY the provided context") 불일관성 방지.
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
    [Comment 5 반영] _get_last_human_content 헬퍼로 메시지 탐색 로직을 분리.
    """
    messages = state.get("messages", [])
    if not messages:
        logger.debug("[Router] 메시지가 없어 responder로 라우팅")
        return "responder"

    user_query = _get_last_human_content(messages)
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
    - 헬퍼를 조합하여 도구 호출 여부를 판단하고 search_context를 갱신합니다.
    - 실패 여부는 planner_failed 플래그로만 관리하며 search_context를 오염시키지 않습니다.

    [Engineering Decision - Coupling]
    현재 ChatService._get_llm을 통해 LLM을 획득합니다.
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
    plan_messages = _build_planner_messages(state)

    search_context, planner_failed, planner_error_message = (
        await _run_planner_with_tools(plan_messages, base_context)
    )

    return {
        "search_context": search_context,
        "planner_failed": planner_failed,
        "planner_error_message": planner_error_message,
    }


async def responder_node(state: AgentState) -> Dict[str, Any]:
    """
    응답 생성자(Responder) 노드 — Thin Orchestrator:
    - Planner가 수집한 context와 대화 이력을 융합하여 최종 응답을 생성합니다.
    - planner_failed 플래그로 폴백 여부를 판단하며, search_context 내부를 검사하지 않습니다.

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
            extra={"error_type": type(e).__name__},
        )
        final_answer = (
            "죄송합니다, 현재 트래픽이 많거나 응답 생성 중에 내부적인 통신 오류가 발생했습니다. "
            "잠시 후 다시 시도해 주시기 바랍니다."
        )

    return {
        "messages": [AIMessage(content=final_answer)],
        "final_answer": final_answer,
    }

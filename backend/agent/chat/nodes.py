# backend/agent/chat/nodes.py

import re
import logging
import numbers
from itertools import islice
from typing import Dict, Any, Literal, cast, List, TypedDict
from langchain_core.messages import AIMessage, SystemMessage, BaseMessage  # type: ignore[import, import-untyped, reportMissingImports]

from backend.agent.chat.state import AgentState  # type: ignore[import, import-untyped, reportMissingImports]
from backend.agent.chat.tools import search_documents_tool, deep_web_search_tool  # type: ignore[import, import-untyped, reportMissingImports]
from backend.services.chat_service import get_chat_service  # type: ignore[import, import-untyped, reportMissingImports]
from backend.api.models.shared import RATING_DOWN  # type: ignore[import, import-untyped, reportMissingImports]

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

# Fallback Routing 관련 임계치 및 윈도우 사이즈
FALLBACK_WINDOW_SIZE: int = 3
FALLBACK_THRESHOLD: int = 2

# 구성 오류 방지를 위한 불변 조건(Invariant): threshold는 window size를 초과할 수 없음
if FALLBACK_THRESHOLD > FALLBACK_WINDOW_SIZE:
    raise ValueError(
        f"Invalid fallback configuration: FALLBACK_THRESHOLD ({FALLBACK_THRESHOLD}) "
        f"must be <= FALLBACK_WINDOW_SIZE ({FALLBACK_WINDOW_SIZE})"
    )

# 라우트 타겟 식별자 식별자(Route Target Identifiers) - 오타 방지 및 단일 진실 공급원
FallbackRoute = Literal["fallback_search", "standard_rag"]
ROUTE_FALLBACK_SEARCH: FallbackRoute = "fallback_search"
ROUTE_STANDARD_RAG: FallbackRoute = "standard_rag"

# 모듈 로드 시 한글 인사말 조합 생성 (O(1) 탐색, 합성어 오탐 차단)
_KOREAN_GREETING_FORMS = {
    base + suffix for base in _SIMPLE_KOREAN_GREETINGS for suffix in _KOREAN_SUFFIXES
}
_LATIN_GREETING_SET = set(_SIMPLE_LATIN_GREETINGS)

# [Engineering Decision] 에러 메시지 로깅 시 PII 보호를 위한 설정
_MAX_ERROR_MSG_CHARS: int = 200
_E164_MAX_DIGITS: int = 15  # 국제 전화번호 표준 최대 자릿수

# [Engineering Decision] 고빈도 로깅 경로의 성능 최적화를 위한 정규식 프리컴파일
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# [Engineering Decision] PII 마스킹 정규식 정책 및 VERBOSE 구조화
# - 의도적 제외: 6자리 이하의 단순 숫자 시퀀스(ID, 순번 등)는 마스킹하지 않음.
# - 의도적 제외: E.164 표준(\`_E164_MAX_DIGITS\`자)을 초과하는 \`_E164_MAX_DIGITS + 1\`자리 이상의 연속 숫자는 엄격히 제외.

def _build_e164_exclusion_lookahead(max_digits: int) -> str:
    """
    데이터 ID, 타임스탬프 등 전화번호 표준(E.164)을 초과하는 
    긴 숫자 시퀀스를 제외하기 위한 부정 룩어헤드 패턴을 생성합니다.
    
    Args:
        max_digits: 허용되는 최대 숫자 자릿수. (정수 계열 타입)

    Raises:
        TypeError: max_digits가 정수 계열(numbers.Integral)이 아니거나 불리언(bool)일 때 발생.
        ValueError: max_digits가 0 이하일 때 발생.
    """
    # [Engineering Decision] bool을 정수형에서 명시적으로 먼저 걸러내어 타입 의미론적 명확성 확보 (numbers.Integral 호환)
    if isinstance(max_digits, bool) or not isinstance(max_digits, numbers.Integral):
        raise TypeError(
            f"max_digits must be an integral type (excluding bool), but got {type(max_digits).__name__}: {max_digits}"
        )
    
    if max_digits <= 0:
        raise ValueError(f"max_digits must be a positive integer, but got: {max_digits}")
    return rf"""
    (?!                                         # [Negative Lookahead]
        (?:\D?\d){{{max_digits + 1},}}            # (구분자?\d) 패턴이 상한({max_digits}+1) 이상 반복 검사
        (?!\d)                                  # 독립된 긴 시퀀스인 경우 매칭 거부
    )
    """

# [Negative Lookahead 패턴] 
_E164_EXCLUSION_LOOKAHEAD = _build_e164_exclusion_lookahead(_E164_MAX_DIGITS)

_PHONE_PATTERN = re.compile(
    rf"""
    (?<!\d)                                     # 앞에 숫자가 없어야 함
    (?:{_E164_EXCLUSION_LOOKAHEAD})              # [Explicit Boundary] _E164_MAX_DIGITS 초과 시퀀스 차단 블록
    (?:\+?\d{{1,3}}[- .]?)?                     # 선택적인 국가 코드 (+82 등)
    \(?0?\d{{1,4}}\)?                           # 지역번호 또는 서비스 번호 (010, 02 등)
    [- .]?\d{{3,5}}                             # 중간 마디 (국제 규격 대응을 위해 5자리까지 허용)
    [- .]?\d{{4}}                               # 끝 마디
    (?!\d)                                      # 뒤에 숫자가 없어야 함
    """,
    re.VERBOSE,
)
_TOKEN_PATTERN = re.compile(r"\b[0-9A-Za-z]{32,}\b")


# ─────────────────────────────────────────────────────────────────────────────
# 타입 정의 및 공통 헬퍼
# ─────────────────────────────────────────────────────────────────────────────


class PlannerResult(TypedDict):
    """Planner 노드의 실행 결과를 명시하고 가독성을 높이기 위한 TypedDict"""

    search_context: str
    planner_failed: bool
    planner_error_message: str
    source_documents: list[dict]


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


def _sanitize_pii_in_text(text: str) -> str:
    """
    텍스트 내의 이메일, 전화번호, 인증 토큰 등 민감 정보(PII)를 탐지하여 마스킹합니다.
    """
    # 1. 이메일 주소 마스킹
    sanitized = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)

    # 2. 한국/국제 전화번호 마스킹 (프리컴파일 패턴 사용)
    sanitized = _PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)

    # 3. 토큰/해시 마스킹 (32자 이상)
    sanitized = _TOKEN_PATTERN.sub("[REDACTED_TOKEN]", sanitized)

    return sanitized


def _safe_truncate_error_msg(e: Exception, max_chars: int = _MAX_ERROR_MSG_CHARS) -> str:
    """
    Exception 객체의 PII 유출을 방지하기 위해 마스킹 처리 후 앞부분만 안전하게 잘라 반환합니다.
    """
    sanitized = _sanitize_pii_in_text(str(e))
    # Pyre2 String Slicing TypeError 우회를 위해 islice 사용
    return "".join(islice(sanitized, max_chars))


async def _run_search_agent(
    plan_messages: List[BaseMessage],
    base_context: str,
    search_tool: Any,
    expected_tool_name: str,
) -> PlannerResult:
    """
    LLM에 도구 호출 권한을 부여하고, 도구를 실행하여 search_context를 반환하는 오케스트레이션 헬퍼.
    """
    chat_svc = get_chat_service()
    llm = chat_svc._get_llm(streaming=False)
    llm_with_tools = llm.bind_tools([search_tool])

    ctx_parts: List[str] = [base_context] if base_context else []
    planner_failed = False
    planner_error_message = ""
    source_documents: List[dict] = []

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
                raw_args = tool_call.get("args")

                if raw_args is None:
                    logger.debug(
                        "[Tool Dispatch] 전달된 args가 없어 빈 dict로 초기화합니다.",
                        extra={"tool_name": tool_name},
                    )
                    tool_args = {}
                elif not isinstance(raw_args, dict):
                    logger.warning(
                        "[Tool Dispatch] 예상치 못한 args 타입 무시",
                        extra={
                            "tool_name": tool_name,
                            "args_type": type(raw_args).__name__,
                        },
                    )
                    continue
                else:
                    tool_args = raw_args

                if tool_name != expected_tool_name:
                    logger.debug(
                        "[Tool Dispatch] 미지원 도구 요청 무시",
                        extra={"tool_name": tool_name},
                    )
                    continue

                query_arg = str(tool_args.get("query", ""))
                logger.info(
                    f"[Planner] -> {expected_tool_name} 호출",
                    extra={"query_length": len(query_arg)},
                )
                tool_res_raw = await search_tool.ainvoke(tool_args)
                tool_res: str = ""
                if isinstance(tool_res_raw, dict):
                    tool_res = str(tool_res_raw.get("context", ""))
                    docs_chunk = tool_res_raw.get("docs", [])
                    if isinstance(docs_chunk, list):
                        source_documents.extend(docs_chunk)
                else:
                    tool_res = str(tool_res_raw)

                ctx_parts.append(
                    f"\n[검색 결과 (쿼리 길이: {len(query_arg)}자)]\n{tool_res}\n"
                )
        else:
            logger.info("[Planner] LLM이 도구 없이 자체 판단 가능으로 결론내렸습니다.")
    except Exception as e:
        # 디버깅을 위해 예외 메시지는 안전하게(truncate) 로그에 남긴다.
        logger.error(
            "[Planner] LLM 추론 중 에러 발생",
            extra={
                "error_type": type(e).__name__,
                # PII 노출 방지를 위해 정제 및 잘라냄 (Pyre2 우회)
                "error_msg": _safe_truncate_error_msg(e),
                "security": "Traceback omitted for PII protection; error_msg sanitized and truncated",
            },
        )
        planner_failed = True
        planner_error_message = "Planner 실행 중 오류가 발생했습니다. 검색 결과 없이 직접 응답을 시도합니다."

    raw_context = _truncate_context("".join(ctx_parts).strip())
    return {
        "search_context": raw_context,
        "planner_failed": planner_failed,
        "planner_error_message": planner_error_message,
        "source_documents": source_documents,
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


def should_fallback(state: AgentState) -> FallbackRoute:
    """
    피드백 기반 Fallback 분기 라우터:
    엄격한 시간적 윈도우(최근 FALLBACK_WINDOW_SIZE 회 세션) 내에서 
    'down'이 기준치(FALLBACK_THRESHOLD) 이상이면 fallback_search, 아니면 standard_rag 반환.
    """
    feedback_history = state.get("feedback_history", [])
    
    # 윈도우 왜곡(Window Distortion) 방지 및 메모리 할당 최적화
    # 전체를 검증 후 자르는 것이 아니라, 최신 N개를 먼저 확보한 뒤 내부에서 타입 가드를 수행합니다.
    recent_feedbacks = feedback_history[-FALLBACK_WINDOW_SIZE:] if feedback_history else []
    
    negative_count = sum(
        1 for f in recent_feedbacks 
        if isinstance(f, dict) and f.get("rating") == RATING_DOWN
    )
    
    if negative_count >= FALLBACK_THRESHOLD:
        logger.warning(
            f"[Router] 최근 {FALLBACK_WINDOW_SIZE}개 중 부정적 피드백 {FALLBACK_THRESHOLD}개 이상 감지. {ROUTE_FALLBACK_SEARCH} 실행.",
            extra={"negative_count": negative_count}
        )
        return ROUTE_FALLBACK_SEARCH
    
    return ROUTE_STANDARD_RAG


def router_edge(state: AgentState) -> Literal["standard_rag", "fallback_search", "responder"]:
    """
    조건부 엣지(Conditional Edge):
    가장 마지막 Human 메시지의 의도를 파악하여
    단순 인사말인 경우 responder로 직행하고, 그렇지 않은 경우 
    과거 피드백 기록에 따라 standard_rag 또는 fallback_search를 결정합니다.
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

    router_log_extra["target"] = "search"
    logger.info("[Router] 검색/추론 도구 필요 판단 -> should_fallback 분기로 전달", extra=router_log_extra)
    return should_fallback(state)


async def standard_rag_node(state: AgentState) -> PlannerResult:
    """
    기존 RAG (Standard RAG) 노드 — Thin Orchestrator:
    - 상태를 수집하고 헬퍼를 호출하여 도구 실행 및 컨텍스트를 구성한 후 반환합니다.
    """
    logger.info("[Standard RAG Node] 실행 중... (도구 호출 및 검색 활용 계획)")

    messages = state.get("messages", [])
    if not messages:
        return {
            "search_context": "",
            "planner_failed": False,
            "planner_error_message": "",
            "source_documents": [],
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

    result = await _run_search_agent(plan_messages, base_context, search_documents_tool, "search_documents_tool")
    return {
        "search_context": result["search_context"],
        "planner_failed": result["planner_failed"],
        "planner_error_message": result["planner_error_message"],
        "source_documents": cast(list[dict], result.get("source_documents", [])),
    }


async def fallback_search_node(state: AgentState) -> PlannerResult:
    """
    딥웹 검출(Fallback Search) 노드 — Thin Orchestrator:
    지속적인 부정적 피드백으로 감지되었을 때 호출되는 타빌리 검색 기반의 보완 노드입니다.
    """
    logger.info("[Fallback Search Node] 실행 중... (Tavily 연동 웹 검색 진행)")

    messages = state.get("messages", [])
    if not messages:
        return {
            "search_context": "",
            "planner_failed": False,
            "planner_error_message": "",
            "source_documents": [],
        }

    base_context = str(state.get("search_context", "") or "")

    sys_prompt = SystemMessage(
        content=(
            "당신은 사용자의 질문을 분석하고 웹 상의 최신 지식이 필요한 경우 적절한 도구를 실행하여 정보를 수집하는 Planner입니다.\n"
            "일반적인 내부 문서(RAG) 검색으로는 사용자를 만족시키기 어렵다고 판단되어 현재 Fallback 외부 검색(웹 검색) 라우팅을 탔습니다.\n"
            "질문에 답하기 위해 최신 뉴스, 외부 트렌드, 정보가 필요하다면 즉시 'deep_web_search_tool'을 호출하세요."
        )
    )
    plan_messages = [sys_prompt] + messages

    result = await _run_search_agent(plan_messages, base_context, deep_web_search_tool, "deep_web_search_tool")
    return {
        "search_context": result["search_context"],
        "planner_failed": result["planner_failed"],
        "planner_error_message": result["planner_error_message"],
        "source_documents": cast(list[dict], result.get("source_documents", [])),
    }


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

    llm = chat_svc._get_llm(streaming=True)
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
        # 디버깅을 위해 예외 메시지는 안전하게(truncate) 로그에 남긴다.
        logger.error(
            "[Responder Node] LLM 응답 생성 실패",
            extra={
                "error_type": type(e).__name__,
                # PII 노출 방지를 위해 정제 및 잘라냄 (Pyre2 우회)
                "error_msg": _safe_truncate_error_msg(e),
                "security": "Traceback omitted for PII protection; error_msg sanitized and truncated",
            },
        )
        final_answer = (
            "죄송합니다, 현재 트래픽이 많거나 응답 생성 중에 내부적인 통신 오류가 발생했습니다. "
            "잠시 후 다시 시도해 주시기 바랍니다."
        )

    return {
        "messages": [AIMessage(content=final_answer)],
        "final_answer": final_answer,
    }

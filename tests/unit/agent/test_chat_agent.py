import copy
import re
import unittest
from itertools import islice
from typing import Any, Awaitable, Callable, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import (  # type: ignore[import, import-untyped, reportMissingImports]
    AIMessage,
    HumanMessage,
)

from backend.agent.chat.nodes import (  # type: ignore[import, import-untyped, reportMissingImports]
    FALLBACK_THRESHOLD,
    ROUTE_FALLBACK_SEARCH,
    ROUTE_STANDARD_RAG,
    fallback_search_node,
    responder_node,
    router_edge,
    standard_rag_node,
)
from backend.agent.chat.state import (  # type: ignore[import, import-untyped, reportMissingImports]
    AgentState,
    FeedbackEntry,
)
from backend.api.models.shared import (  # type: ignore[import, import-untyped, reportMissingImports]
    RATING_DOWN,
)

# -------------------------------------------------------------------------
# 시스템 규약 (Contracts): 노드 출력 포맷, 라우팅 식별자 및 테스트 상수
# -------------------------------------------------------------------------
# [검색 결과 (쿼리 길이: \d+자)] 패턴 (하드코딩 방지 및 재사용성 확보)
PLANNER_HEADER_PATTERN = re.compile(r"\[검색 결과 \(쿼리 길이: \d+자\)\]")

_ROUTE_RESPONDER = "responder"
_TOOL_SEARCH_DOCUMENTS = "search_documents_tool"
_TOOL_DEEP_WEB_SEARCH = "deep_web_search_tool"

_TEST_USER_ID = "anonymized_user_001"
_TEST_SESSION_ID = "anonymized_session_001"
_TEST_CALL_ID = "call_test_001"
_TEST_FEEDBACK_TS = "2026-01-01T00:00:00Z"

_PLANNER_FAIL_SUBSTRING = "Planner 실행에 실패했습니다"
_RESPONDER_FAIL_SUBSTRING = "오류가 발생했습니다"


class TestChatAgent(unittest.IsolatedAsyncioTestCase):
    """
    채팅 에이전트의 노드 실행(standard_rag_node, fallback_search_node, responder_node) 및
    라우팅(router_edge) 로직을 검증하는 단위 테스트 클래스.
    모든 테스트는 독립성을 보장하기 위해 AgentState를 deepcopy하여 사용하며,
    CI 환경에서의 디버깅 편의성을 위해 요약된 실패 메시지를 제공합니다.
    """

    def setUp(self) -> None:
        self.user_id = _TEST_USER_ID
        self.session_id = _TEST_SESSION_ID
        self.base_state: AgentState = {
            "messages": [],
            "user_id": self.user_id,
            "session_id": self.session_id,
            "search_context": "",
            "planner_failed": False,
            "planner_error_message": "",
            "source_documents": [],
            "feedback_history": [],
        }

    # -------------------------------------------------------------------------
    # 0. Test Helpers & Assert Encapsulation
    # -------------------------------------------------------------------------
    def _build_state(
        self,
        query: Optional[str] = None,
        search_context: str = "",
        feedback_history: Optional[List[FeedbackEntry]] = None,
    ) -> AgentState:
        """독립적인 AgentState 복사본을 생성하는 팩토리 헬퍼."""
        state = copy.deepcopy(self.base_state)
        if query is not None:
            state["messages"] = [HumanMessage(content=query)]
        if search_context:
            state["search_context"] = search_context
        if feedback_history is not None:
            state["feedback_history"] = copy.deepcopy(feedback_history)
        return state

    @staticmethod
    def _build_negative_feedback_history(count: int) -> List[FeedbackEntry]:
        """부정 피드백 이력을 생성하는 헬퍼 (PII 미포함 합성 데이터)."""
        return [
            {
                "message_id": f"msg_{idx}",
                "rating": RATING_DOWN,
                "text": None,
                "timestamp": _TEST_FEEDBACK_TS,
            }
            for idx in range(count)
        ]

    @staticmethod
    def _configure_llm_service_mock(
        mock_get_svc: MagicMock,
        *,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        side_effect: Optional[Exception] = None,
        response_content: str = "",
    ) -> MagicMock:
        """ChatService 및 LLM 모킹 설정을 캡슐화한 헬퍼."""
        mock_svc = MagicMock()
        mock_llm = MagicMock()
        mock_get_svc.return_value = mock_svc
        mock_svc._get_llm.return_value = mock_llm
        mock_svc._get_user_context_prompt_text.return_value = "User context summary."

        llm_with_tools = MagicMock()
        if side_effect is not None:
            mock_llm.ainvoke = AsyncMock(side_effect=side_effect)
            llm_with_tools.ainvoke = AsyncMock(side_effect=side_effect)
        else:
            mock_llm.ainvoke = AsyncMock(
                return_value=AIMessage(content=response_content)
            )
            mock_llm_response = MagicMock(spec=AIMessage)
            mock_llm_response.content = response_content
            mock_llm_response.tool_calls = tool_calls or []
            llm_with_tools.ainvoke = AsyncMock(return_value=mock_llm_response)

        mock_llm.bind_tools.return_value = llm_with_tools
        return mock_svc

    def _summarize_messages(self, messages: List[Any], limit: int = 5) -> str:
        """대규모 메시지 리스트를 디버깅용으로 요약하여 반환 (가독성 증대 및 로그 오염 방지)."""
        if not messages:
            return "[]"
        summary = []
        for msg in messages[-limit:]:
            m_type = type(msg).__name__
            # [Pyre2 Workaround] Pyre2의 str 슬라이싱 버그 우회를 위해 islice 사용
            content_str = str(getattr(msg, "content", ""))
            content_preview = "".join(islice(content_str, 20)).replace("\n", " ")
            summary.append(f"{m_type}('{content_preview}...')")  # type: ignore[arg-type]

        prefix = f"(showing last {limit}) " if len(messages) > limit else ""
        return prefix + " -> ".join(summary)

    def _assert_search_context_structure(
        self, context: str, expected_content_keyword: str
    ) -> None:
        """검색 노드의 검색 결과 포맷이 시스템 규칙(정규식 패턴)을 따르는지 검증."""
        self.assertIsNotNone(
            PLANNER_HEADER_PATTERN.search(context),
            f"검색 결과 헤더 포맷이 올바르지 않습니다. got={context!r}",
        )
        self.assertIn(
            expected_content_keyword,
            context,
            "검색 결과 내에 핵심 키워드가 포함되어 있지 않습니다.",
        )

    def _assert_responder_wiring(
        self, result: Dict[str, Any], expected_llm_output: str
    ) -> None:
        """responder_node가 LLM 출력을 정확한 위치(마지막 메시지)에 적재했는지 검증."""
        final_answer = result.get("final_answer", "")
        self.assertTrue(len(final_answer) > 0, "최종 답변이 비어있습니다.")
        self.assertIn(
            expected_llm_output,
            final_answer,
            "LLM 응답 내용이 최종 답변 필드에 전달되지 않았습니다.",
        )

        ans_messages = result.get("messages", [])
        self.assertTrue(len(ans_messages) > 0, "결과 메시지 리스트가 비어있습니다.")

        # [Strict Check] any() 대신 '마지막' 메시지를 타겟팅하여 오탐 방지 (Future-proofing)
        last_msg = ans_messages[-1]
        msg_summary = self._summarize_messages(ans_messages)

        self.assertIsInstance(
            last_msg,
            AIMessage,
            f"마지막 메시지가 AIMessage가 아닙니다. (요약: {msg_summary})",
        )
        self.assertIn(
            expected_llm_output,
            str(getattr(last_msg, "content", "")),
            f"최신 AIMessage 내에 예상된 답변이 포함되어 있지 않습니다. (요약: {msg_summary})",
        )

    async def _run_and_verify_search_node_success(
        self,
        node_fn: Callable[[AgentState], Awaitable[Any]],
        mock_tool: MagicMock,
        mock_get_svc: MagicMock,
        *,
        tool_name: str,
        query_keyword: str,
        tool_context: str,
        existing_search_context: str,
        expect_existing_context_retained: bool,
    ) -> None:
        """standard_rag_node / fallback_search_node 성공 경로의 공통 검증 헬퍼."""
        tool_call = {
            "name": tool_name,
            "args": {"query": query_keyword},
            "id": _TEST_CALL_ID,
        }
        self._configure_llm_service_mock(mock_get_svc, tool_calls=[tool_call])
        mock_tool.ainvoke = AsyncMock(
            return_value={
                "context": tool_context,
                "docs": [
                    {"id": "doc1", "content": tool_context},
                    "invalid_non_dict_entry",
                ],
            }
        )

        state = self._build_state(
            query="보고서 관련 내용을 알려줘",
            search_context=existing_search_context,
        )
        result = await node_fn(state)

        search_context = result.get("search_context", "")
        self._assert_search_context_structure(search_context, tool_context)
        if expect_existing_context_retained:
            self.assertIn(existing_search_context, search_context)
        else:
            self.assertNotIn(existing_search_context, search_context)

        # 비-dict 요소가 _normalize_source_docs에 의해 제거되었는지 확인
        self.assertEqual(len(result.get("source_documents", [])), 1)
        self.assertFalse(result.get("planner_failed", False))
        mock_tool.ainvoke.assert_called_once_with({"query": query_keyword})

    async def _run_and_verify_search_node_failure(
        self,
        node_fn: Callable[[AgentState], Awaitable[Any]],
        mock_get_svc: MagicMock,
        *,
        exc: Exception,
        expected_context: str = "",
        initial_context: str = "",
    ) -> None:
        """검색 노드 예외 발생 시 Fail-safe 및 상태 격리를 검증하는 헬퍼."""
        self._configure_llm_service_mock(mock_get_svc, side_effect=exc)
        state = self._build_state(
            query="실패 복원력 테스트 질의",
            search_context=initial_context,
        )

        result = await node_fn(state)

        self.assertTrue(result.get("planner_failed"))
        self.assertIn(
            _PLANNER_FAIL_SUBSTRING,
            str(result.get("planner_error_message", "")),
        )
        self.assertEqual(result.get("search_context"), expected_context)
        self.assertEqual(result.get("source_documents"), [])

    # -------------------------------------------------------------------------
    # 1. Router Edge Tests (Scenario Check)
    # -------------------------------------------------------------------------
    def test_router_greeting_scenario(self) -> None:
        """일상 대화(인사) 시 responder로 라우팅되는지 확인."""
        state = self._build_state(query="안녕! 반가워.")
        self.assertEqual(router_edge(state), _ROUTE_RESPONDER)

    def test_router_empty_messages_scenario(self) -> None:
        """메시지가 비어 있을 때 responder로 안전하게 라우팅되는지 확인."""
        state = self._build_state(query=None)
        self.assertEqual(router_edge(state), _ROUTE_RESPONDER)

    def test_router_query_scenario(self) -> None:
        """지식 검색이 필요한 질문 시 기본 standard_rag로 라우팅되는지 확인."""
        state = self._build_state(query="오늘의 업무 보고서 내용을 알려줘.")
        self.assertEqual(router_edge(state), ROUTE_STANDARD_RAG)

    def test_router_complex_reasoning_scenario(self) -> None:
        """복잡한 추론이 필요한 질문 시 standard_rag로 라우팅되는지 확인."""
        state = self._build_state(
            query="지난주 판매 데이터를 분석해서 이번주 전략을 세워줘."
        )
        self.assertEqual(router_edge(state), ROUTE_STANDARD_RAG)

    def test_router_negative_feedback_fallback_scenario(self) -> None:
        """최근 부정 피드백이 임계치 이상 누적되면 fallback_search로 라우팅되는지 확인."""
        state = self._build_state(
            query="프로젝트 A 최신 일정을 알려줘.",
            feedback_history=self._build_negative_feedback_history(FALLBACK_THRESHOLD),
        )
        self.assertEqual(router_edge(state), ROUTE_FALLBACK_SEARCH)

    # -------------------------------------------------------------------------
    # 2. Node Execution & State Transition Tests (Mock LLM)
    # -------------------------------------------------------------------------
    @patch("backend.agent.chat.nodes.get_chat_service")
    @patch("backend.agent.chat.nodes.search_documents_tool")
    async def test_standard_rag_node_success_with_tool(
        self, mock_tool: MagicMock, mock_get_svc: MagicMock
    ) -> None:
        """standard_rag_node가 내부 검색 도구를 호출하고 기존 문맥과 함께 컨텍스트를 구성하는지 검증."""
        await self._run_and_verify_search_node_success(
            standard_rag_node,
            mock_tool,
            mock_get_svc,
            tool_name=_TOOL_SEARCH_DOCUMENTS,
            query_keyword="업무 보고서",
            tool_context="3/18 업무 보고서: 프로젝트 A 진행 중.",
            existing_search_context="기존 대화 요약 문맥",
            expect_existing_context_retained=True,
        )

    @patch("backend.agent.chat.nodes.get_chat_service")
    @patch("backend.agent.chat.nodes.deep_web_search_tool")
    async def test_fallback_search_node_success_with_tool(
        self, mock_tool: MagicMock, mock_get_svc: MagicMock
    ) -> None:
        """fallback_search_node가 웹 검색 도구를 호출하고 기존 RAG 문맥 오염 없이 결과를 구성하는지 검증."""
        await self._run_and_verify_search_node_success(
            fallback_search_node,
            mock_tool,
            mock_get_svc,
            tool_name=_TOOL_DEEP_WEB_SEARCH,
            query_keyword="최신 AI 트렌드",
            tool_context="외부 검색 요약: 최신 AI 동향 리포트.",
            existing_search_context="이전 실패한 RAG 문맥",
            expect_existing_context_retained=False,
        )

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_search_nodes_empty_messages_early_return(
        self, mock_get_svc: MagicMock
    ) -> None:
        """메시지가 비어 있을 때 LLM 호출 없이 초기 상태를 반환하는지 검증."""
        empty_state = self._build_state(query=None)
        for node_fn in (standard_rag_node, fallback_search_node):
            result = await node_fn(empty_state)
            self.assertEqual(result.get("search_context"), "")
            self.assertFalse(result.get("planner_failed"))
            self.assertEqual(result.get("source_documents"), [])
        mock_get_svc.assert_not_called()

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_standard_rag_node_failure_handling(
        self, mock_get_svc: MagicMock
    ) -> None:
        """standard_rag_node 장애 시 Fail-safe가 작동하며 기존 문맥이 보존되는지 검증."""
        await self._run_and_verify_search_node_failure(
            standard_rag_node,
            mock_get_svc,
            exc=RuntimeError("API Connection Error"),
            expected_context="보존될 기존 문맥",
            initial_context="보존될 기존 문맥",
        )

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_fallback_search_node_failure_handling(
        self, mock_get_svc: MagicMock
    ) -> None:
        """fallback_search_node 네트워크 장애 시 Fail-safe가 작동하며 오염 없이 빈 문맥을 반환하는지 검증."""
        await self._run_and_verify_search_node_failure(
            fallback_search_node,
            mock_get_svc,
            exc=TimeoutError("Request timed out"),
            expected_context="",
            initial_context="격리되어야 할 이전 RAG 문맥",
        )

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_responder_node_state_transition(
        self, mock_get_svc: MagicMock
    ) -> None:
        """responder_node의 배선 및 답변 생성 무결성 검증."""
        llm_output = "보고서에 따르면 프로젝트 A가 진행 중입니다."
        self._configure_llm_service_mock(mock_get_svc, response_content=llm_output)

        state = self._build_state(
            query="보고서 알려줘", search_context="프로젝트 A 진행 중."
        )
        result = await responder_node(state)
        self._assert_responder_wiring(result, llm_output)

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_responder_node_failure_fallback(
        self, mock_get_svc: MagicMock
    ) -> None:
        """responder_node에서 LLM 예외 발생 시 크래시 대신 안내 문구를 반환하는지 검증."""
        self._configure_llm_service_mock(
            mock_get_svc, side_effect=RuntimeError("Unexpected model error")
        )

        state = self._build_state(query="답변 생성 오류 테스트")
        result = await responder_node(state)
        self._assert_responder_wiring(result, _RESPONDER_FAIL_SUBSTRING)


if __name__ == "__main__":
    unittest.main()

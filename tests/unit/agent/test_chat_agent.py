import unittest
import copy
import re
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage  # type: ignore[import, import-untyped, reportMissingImports]
from backend.agent.chat.nodes import router_edge, planner_node, responder_node  # type: ignore[import, import-untyped, reportMissingImports]
from backend.agent.chat.state import AgentState  # type: ignore[import, import-untyped, reportMissingImports]

class TestChatAgent(unittest.IsolatedAsyncioTestCase):
    """
    채팅 에이전트의 노드 실행 및 라우팅 로직을 검증하는 단위 테스트 클래스.
    모든 테스트는 독립성을 보장하기 위해 AgentState를 deepcopy하여 사용하며,
    시스템 포맷 변경에 유연하게 대응하도록 정규식 기반 검증을 수행합니다.
    """
    def setUp(self):
        self.user_id = "test_user"
        self.session_id = "test_session"
        self.base_state: AgentState = {
            "messages": [],
            "user_id": self.user_id,
            "session_id": self.session_id,
            "search_context": "",
            "planner_failed": False,
            "planner_error_message": "",
            "source_documents": []
        }

    # -------------------------------------------------------------------------
    # 0. Test Assert Helpers (Encapsulation of Brittle Logic)
    # -------------------------------------------------------------------------
    def _assert_search_context_structure(self, context, expected_content_keyword):
        """planner_node의 검색 결과 포맷이 시스템 규칙(정규식 패턴)을 따르는지 검증"""
        # [검색 결과 (쿼리 길이: \d+자)] 패턴 확인 (하드코딩된 문자열 결합 방지)
        header_pattern = r"\[검색 결과 \(쿼리 길이: \d+자\)\]"
        self.assertIsNotNone(re.search(header_pattern, context), "검색 결과 헤더 포맷이 올바르지 않습니다.")
        self.assertIn(expected_content_keyword, context, "검색 결과 내에 핵심 키워드가 포함되어 있지 않습니다.")

    def _assert_responder_wiring(self, result, expected_llm_output):
        """responder_node가 LLM 출력을 오염 없이 전달하고 배선이 올바른지 검증"""
        final_answer = result.get("final_answer", "")
        self.assertTrue(len(final_answer) > 0, "최종 답변이 비어있습니다.")
        # 의미적 내용이 포함되어 있는지 확인 (미세한 문구 변화에 탄력적으로 대응)
        self.assertIn(expected_llm_output, final_answer, "LLM 응답 내용이 최종 답변에 전달되지 않았습니다.")
        
        ans_messages = result.get("messages", [])
        self.assertTrue(len(ans_messages) > 0 and isinstance(ans_messages[0], AIMessage))
        self.assertIn(expected_llm_output, str(ans_messages[0].content))

    # -------------------------------------------------------------------------
    # 1. Router Edge Tests (Scenario Check)
    # -------------------------------------------------------------------------
    def test_router_greeting_scenario(self):
        """일상 대화(인사) 시 responder로 라우팅되는지 확인"""
        state = copy.deepcopy(self.base_state)
        state["messages"] = [HumanMessage(content="안녕! 반가워.")]
        
        result = router_edge(state)
        self.assertEqual(result, "responder")

    def test_router_query_scenario(self):
        """지식 검색이 필요한 질문 시 planner로 라우팅되는지 확인"""
        state = copy.deepcopy(self.base_state)
        state["messages"] = [HumanMessage(content="오늘의 업무 보고서 내용을 알려줘.")]
        
        result = router_edge(state)
        self.assertEqual(result, "planner")

    def test_router_complex_reasoning_scenario(self):
        """복잡한 추론이 필요한 질문 시 planner로 라우팅되는지 확인"""
        state = copy.deepcopy(self.base_state)
        state["messages"] = [HumanMessage(content="지난주 판매 데이터를 분석해서 이번주 전략을 세워줘.")]
        
        result = router_edge(state)
        self.assertEqual(result, "planner")

    # -------------------------------------------------------------------------
    # 2. Node Execution & State Transition Tests (Mock LLM)
    # -------------------------------------------------------------------------
    
    @patch("backend.agent.chat.nodes.get_chat_service")
    @patch("backend.agent.chat.nodes.search_documents_tool")
    async def test_planner_node_success_with_tool(self, mock_tool, mock_get_svc):
        """Planner 노드가 도구를 호출하고 구조화된 컨텍스트를 생성하는지 검증"""
        query_keyword = "업무 보고서"
        mock_svc = MagicMock()
        mock_llm = MagicMock()
        mock_get_svc.return_value = mock_svc
        mock_svc._get_llm.return_value = mock_llm
        
        llm_with_tools = MagicMock()
        llm_with_tools.ainvoke = AsyncMock()
        mock_llm.bind_tools.return_value = llm_with_tools

        mock_tool_call = {
            "name": "search_documents_tool",
            "args": {"query": query_keyword},
            "id": "call_abc123"
        }
        
        mock_llm_response = MagicMock(spec=AIMessage)
        mock_llm_response.content = ""
        mock_llm_response.tool_calls = [mock_tool_call]
        llm_with_tools.ainvoke.return_value = mock_llm_response
        
        mock_tool.ainvoke = AsyncMock(return_value={
            "context": "3/18 업무 보고서: 프로젝트 A 진행 중.",
            "docs": [{"id": "doc1", "content": "..."}]
        })
        
        state = copy.deepcopy(self.base_state)
        state["messages"] = [HumanMessage(content="보고서 알려줘")]
        
        # Execute
        result = await planner_node(state)
        
        # Verify Structure via Helper (Regex 기반 검증)
        self._assert_search_context_structure(result.get("search_context", ""), "3/18 업무 보고서")
        self.assertEqual(len(result.get("source_documents", [])), 1)
        self.assertFalse(result.get("planner_failed", False))
        
        # Strict Argument Check
        mock_tool.ainvoke.assert_called_once_with({"query": query_keyword})

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_planner_node_failure_handling(self, mock_get_svc):
        """LLM 장애 시 Fail-safe가 작동하며 상태 원자성이 유지되는지 검증"""
        mock_svc = MagicMock()
        mock_llm = MagicMock()
        llm_with_tools = MagicMock()
        llm_with_tools.ainvoke = AsyncMock(side_effect=Exception("API Connection Error"))
        
        mock_llm.bind_tools.return_value = llm_with_tools
        mock_get_svc.return_value = mock_svc
        mock_svc._get_llm.return_value = mock_llm
        
        state = copy.deepcopy(self.base_state)
        state["messages"] = [HumanMessage(content="Hello")]
        
        # Execute
        result = await planner_node(state)
        
        # Verify Failure State (Keyword Check)
        self.assertTrue(result.get("planner_failed"))
        self.assertIn("오류가 발생했습니다", str(result.get("planner_error_message", "")))
        
        # Verify Atomic State (No pollution)
        self.assertEqual(result.get("search_context"), state.get("search_context"))
        self.assertEqual(result.get("source_documents"), state.get("source_documents"))

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_responder_node_state_transition(self, mock_get_svc):
        """Responder 노드의 배선 및 답변 생성 무결성 검증"""
        llm_output = "보고서에 따르면 프로젝트 A가 진행 중입니다."

        mock_svc = MagicMock()
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=llm_output))
        
        mock_get_svc.return_value = mock_svc
        mock_svc._get_llm.return_value = mock_llm
        mock_svc._get_user_context_prompt_text.return_value = "User is a manager."
        
        state = copy.deepcopy(self.base_state)
        state["search_context"] = "프로젝트 A 진행 중."
        state["messages"] = [HumanMessage(content="보고서 알려줘")]
        
        result = await responder_node(state)
        
        # Verify Wiring via Helper (Contract Testing)
        self._assert_responder_wiring(result, llm_output)

if __name__ == "__main__":
    unittest.main()

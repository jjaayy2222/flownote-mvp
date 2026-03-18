import unittest
import copy
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage  # type: ignore[import, import-untyped, reportMissingImports]
from backend.agent.chat.nodes import router_edge, planner_node, responder_node  # type: ignore[import, import-untyped, reportMissingImports]
from backend.agent.chat.state import AgentState  # type: ignore[import, import-untyped, reportMissingImports]

class TestChatAgent(unittest.IsolatedAsyncioTestCase):
    """
    채팅 에이전트의 노드 실행 및 라우팅 로직을 검증하는 단위 테스트 클래스.
    모든 테스트는 독립성을 보장하기 위해 AgentState를 deepcopy하여 사용합니다.
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
        """Planner 노드가 도구를 1회 호출하고 상태(search_context)를 정확히 업데이트하는지 검증"""
        # 1. Mock ChatService & LLM
        mock_svc = MagicMock()
        mock_llm = MagicMock()
        mock_get_svc.return_value = mock_svc
        mock_svc._get_llm.return_value = mock_llm
        
        # 2. llm.bind_tools should return a runnable with an async ainvoke
        llm_with_tools = MagicMock()
        llm_with_tools.ainvoke = AsyncMock()
        mock_llm.bind_tools.return_value = llm_with_tools

        # 3. Define the tool call we expect
        mock_tool_call = {
            "name": "search_documents_tool",
            "args": {"query": "업무 보고서"},
            "id": "call_abc123"
        }
        
        # 4. Mock the LLM response containing the tool call
        mock_response = MagicMock(spec=AIMessage)
        mock_response.content = ""
        mock_response.tool_calls = [mock_tool_call]
        llm_with_tools.ainvoke.return_value = mock_response
        
        # 5. Mock the Tool itself (its ainvoke method)
        mock_tool.ainvoke = AsyncMock(return_value={
            "context": "3/18 업무 보고서: 프로젝트 A 진행 중.",
            "docs": [{"id": "doc1", "content": "..."}]
        })
        
        state = copy.deepcopy(self.base_state)
        state["messages"] = [HumanMessage(content="보고서 알려줘")]
        
        # Execute
        result = await planner_node(state)
        
        # Verify State Update
        self.assertIn("3/18 업무 보고서", result.get("search_context", ""))
        self.assertEqual(len(result.get("source_documents", [])), 1)
        self.assertFalse(result.get("planner_failed", False))
        
        # [Strict Check] 인자와 호출 횟수 검증
        mock_tool.ainvoke.assert_called_once_with({"query": "업무 보고서"})

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_planner_node_failure_handling(self, mock_get_svc):
        """LLM 호출 또는 도구 실행 실패 시 planner_failed 플래그와 에러 메시지가 설정되는지 검증 (Fail-safe)"""
        # Mock LLM Exception during ainvoke
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
        
        # Verify Failure State (Atomic Update Check)
        self.assertTrue(result.get("planner_failed"))
        self.assertIn("오류가 발생했습니다", str(result.get("planner_error_message", "")))
        
        # [Strict Check] 실패 시 검색 문맥이나 문서 목록이 오염되지 않았는지(초기값 유지) 검증
        self.assertEqual(result.get("search_context", ""), "")
        self.assertEqual(result.get("source_documents", []), [])

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_responder_node_state_transition(self, mock_get_svc):
        """Responder 노드가 최종 답변을 생성하고 final_answer를 업데이트하는지 확인"""
        # Mock ChatService & LLM
        mock_svc = MagicMock()
        mock_llm = MagicMock()
        # Mock LLM response - AsyncMock 생성 시 return_value를 즉시 할당하여 중복 제거
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="보고서에 따르면 프로젝트 A가 진행 중입니다."))
        
        mock_get_svc.return_value = mock_svc
        mock_svc._get_llm.return_value = mock_llm
        mock_svc._get_user_context_prompt_text.return_value = "User is a manager."
        
        state = copy.deepcopy(self.base_state)
        state["search_context"] = "프로젝트 A 진행 중."
        state["messages"] = [HumanMessage(content="보고서 알려줘")]
        
        result = await responder_node(state)
        
        # Verify State Update
        self.assertEqual(result.get("final_answer"), "보고서에 따르면 프로젝트 A가 진행 중입니다.")
        
        # Null Safety check for message list
        ans_messages = result.get("messages", [])
        self.assertTrue(len(ans_messages) > 0)
        self.assertIsInstance(ans_messages[0], AIMessage)

if __name__ == "__main__":
    unittest.main()

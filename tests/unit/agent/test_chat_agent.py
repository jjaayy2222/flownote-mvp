import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage  # type: ignore[import, import-untyped, reportMissingImports]
from backend.agent.chat.nodes import router_edge, planner_node, responder_node  # type: ignore[import, import-untyped, reportMissingImports]
from backend.agent.chat.state import AgentState  # type: ignore[import, import-untyped, reportMissingImports]

class TestChatAgent(unittest.IsolatedAsyncioTestCase):
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
        state = self.base_state.copy()
        state["messages"] = [HumanMessage(content="안녕! 반가워.")]
        
        result = router_edge(state)
        self.assertEqual(result, "responder")

    def test_router_query_scenario(self):
        """지식 검색이 필요한 질문 시 planner로 라우팅되는지 확인"""
        state = self.base_state.copy()
        state["messages"] = [HumanMessage(content="오늘의 업무 보고서 내용을 알려줘.")]
        
        result = router_edge(state)
        self.assertEqual(result, "planner")

    def test_router_complex_reasoning_scenario(self):
        """복잡한 추론이 필요한 질문 시 planner로 라우팅되는지 확인"""
        state = self.base_state.copy()
        state["messages"] = [HumanMessage(content="지난주 판매 데이터를 분석해서 이번주 전략을 세워줘.")]
        
        result = router_edge(state)
        self.assertEqual(result, "planner")

    # -------------------------------------------------------------------------
    # 2. Node Execution & State Transition Tests (Mock LLM)
    # -------------------------------------------------------------------------
    @patch("backend.agent.chat.nodes.get_chat_service")
    @patch("backend.agent.chat.nodes.search_documents_tool")
    async def test_planner_node_state_transition(self, mock_tool, mock_get_svc):
        """Planner 노드가 도구를 호출하고 상태(search_context)를 업데이트하는지 확인"""
        # 1. Mock ChatService & LLM
        mock_svc = MagicMock()
        mock_llm = MagicMock()  # bind_tools is synchronous
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
        
        state = self.base_state.copy()
        state["messages"] = [HumanMessage(content="보고서 알려줘")]
        
        # Execute
        result = await planner_node(state)
        
        # Verify State Update
        self.assertIn("3/18 업무 보고서", result.get("search_context", ""))
        self.assertEqual(len(result.get("source_documents", [])), 1)
        self.assertFalse(result.get("planner_failed", False))

    @patch("backend.agent.chat.nodes.get_chat_service")
    async def test_responder_node_state_transition(self, mock_get_svc):
        """Responder 노드가 최종 답변을 생성하고 final_answer를 업데이트하는지 확인"""
        # Mock ChatService & LLM
        mock_svc = MagicMock()
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock()
        mock_get_svc.return_value = mock_svc
        mock_svc._get_llm.return_value = mock_llm
        mock_svc._get_user_context_prompt_text.return_value = "User is a manager."
        
        # Mock LLM response
        mock_llm.ainvoke.return_value = AIMessage(content="보고서에 따르면 프로젝트 A가 진행 중입니다.")
        
        state = self.base_state.copy()
        state["search_context"] = "프로젝트 A 진행 중."
        state["messages"] = [HumanMessage(content="보고서 알려줘")]
        
        result = await responder_node(state)
        
        # Verify State Update
        self.assertEqual(result.get("final_answer"), "보고서에 따르면 프로젝트 A가 진행 중입니다.")
        self.assertIsInstance(result["messages"][0], AIMessage)

if __name__ == "__main__":
    unittest.main()

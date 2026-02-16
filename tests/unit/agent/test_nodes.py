import unittest
from unittest.mock import patch, MagicMock
from backend.agent.nodes import analyze_node, classify_node, should_retry

# AgentState는 TypedDict이므로 import만 하면 됨


class TestAgentNodes(unittest.TestCase):

    def setUp(self):
        self.base_state = {
            "file_content": "Sample content",
            "file_name": "test.pdf",
            "extracted_keywords": [],
            "retrieved_context": "",
            "retry_count": 0,
            "confidence_score": 0.0,
        }

    @patch("backend.agent.nodes.extract_keywords")
    def test_analyze_node(self, mock_extract):
        """analyze_node가 keywords를 state에 추가하는지 검증"""
        mock_extract.return_value = ["Keyword1", "Keyword2"]

        # Call analyze_node with base state
        result = analyze_node(self.base_state)

        # Verify extraction result is in the output dict
        self.assertEqual(result["extracted_keywords"], ["Keyword1", "Keyword2"])
        mock_extract.assert_called_once_with("Sample content")

    @patch("backend.agent.nodes.get_llm")
    def test_classify_node_stubs(self, mock_get_llm):
        """LLM 초기화 실패 시 Stub 반환 검증 (Fail-safe)"""
        mock_get_llm.return_value = None

        result = classify_node(self.base_state)

        # Stub 값 확인
        classification_result = result.get("classification_result", {})
        self.assertEqual(classification_result.get("category"), "Resources")
        self.assertEqual(result.get("confidence_score"), 0.0)
        self.assertIn("initialization failed", result.get("reasoning", ""))

    def test_should_retry_logic(self):
        """should_retry 조건 분기 테스트"""
        # Case 1: High Confidence -> End (0.8 >= 0.7)
        state_high = {**self.base_state, "confidence_score": 0.8}
        self.assertEqual(should_retry(state_high), "end")

        # Case 2: Low Confidence, Zero Retry -> Retry (0.5 < 0.7, 0 < 3)
        state_low = {**self.base_state, "confidence_score": 0.5, "retry_count": 0}
        self.assertEqual(should_retry(state_low), "retry")

        # Case 3: Low Confidence, Max Retry -> End (3 >= 3)
        state_max = {**self.base_state, "confidence_score": 0.5, "retry_count": 3}
        self.assertEqual(should_retry(state_max), "end")

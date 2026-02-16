import unittest
from unittest.mock import patch
from backend.agent.utils import extract_keywords, search_similar_docs


class TestAgentUtils(unittest.TestCase):

    def test_search_similar_docs(self):
        """키워드가 있을 때 Mock Context 반환 검증"""
        keywords = ["AI", "Agent"]
        result = search_similar_docs(keywords)
        self.assertIn("Retrieved Context", result)
        self.assertIn("AI", result)

    def test_search_similar_docs_empty(self):
        """키워드가 없을 때 빈 문자열 반환 검증"""
        self.assertEqual(search_similar_docs([]), "")

    @patch("backend.agent.utils.get_llm")
    def test_extract_keywords_llm_fallback(self, mock_get_llm):
        """LLM 사용 불가 시 Regex Fallback 동작 및 한글 지원 검증"""
        # LLM 초기화 실패(None) 시뮬레이션 -> Fallback Trigger
        mock_get_llm.return_value = None

        text = "This is a complex System Architecture for FlowNote. 중요한 문서입니다."
        keywords = extract_keywords(text)

        # Regex 추출 결과 검증:
        # 1. 대문자로 시작하는 영단어 (System, Architecture, FlowNote)
        # 2. 한글 2글자 이상 (중요한, 문서입니다)
        self.assertIn("FlowNote", keywords)
        self.assertIn("System", keywords)
        self.assertIn("Architecture", keywords)
        self.assertIn("중요한", keywords)
        self.assertIn("문서입니다", keywords)

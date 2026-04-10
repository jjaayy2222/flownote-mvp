# tests/unit/agent/chat/test_nodes.py

import unittest
from backend.agent.chat.nodes import (
    should_fallback,
    ROUTE_FALLBACK_SEARCH,
    ROUTE_STANDARD_RAG,
    FALLBACK_WINDOW_SIZE,
    FALLBACK_THRESHOLD,
)
from backend.api.models.shared import RATING_DOWN, RATING_UP


class TestChatNodes(unittest.TestCase):
    def _make_history(self, count: int, **kwargs) -> list[dict]:
        """Factory helper to build a list of feedback dictionaries with arbitrary keys."""
        return [kwargs.copy() for _ in range(count)]

    def test_should_fallback_no_history(self):
        state = {"feedback_history": []}
        self.assertEqual(should_fallback(state), ROUTE_STANDARD_RAG)

    def test_should_fallback_under_threshold(self):
        # 1 under the threshold should route to standard RAG
        downs = self._make_history(count=(FALLBACK_THRESHOLD - 1), rating=RATING_DOWN)
        state = {"feedback_history": downs}
        self.assertEqual(should_fallback(state), ROUTE_STANDARD_RAG)

    def test_should_fallback_reach_threshold(self):
        # exactly the threshold should route to fallback search
        downs = self._make_history(count=FALLBACK_THRESHOLD, rating=RATING_DOWN)
        state = {"feedback_history": downs}
        self.assertEqual(should_fallback(state), ROUTE_FALLBACK_SEARCH)

    def test_should_fallback_exceed_threshold(self):
        # more than the threshold (e.g., threshold + 1) should also route to fallback, checking against == vs >= error
        downs = self._make_history(count=(FALLBACK_THRESHOLD + 1), rating=RATING_DOWN)
        state = {"feedback_history": downs}
        self.assertEqual(should_fallback(state), ROUTE_FALLBACK_SEARCH)

    def test_should_fallback_mixed_recent(self):
        # Window size of feedback containing exactly threshold downs at the end
        history = self._make_history(count=(FALLBACK_WINDOW_SIZE - FALLBACK_THRESHOLD), rating=RATING_UP)
        history.extend(self._make_history(count=FALLBACK_THRESHOLD, rating=RATING_DOWN))
        state = {"feedback_history": history}
        self.assertEqual(should_fallback(state), ROUTE_FALLBACK_SEARCH)

    def test_should_fallback_old_downs(self):
        # downs that are older than the window size should be ignored.
        # we put THRESHOLD downs at the very beginning (oldest), and UP for the entire window
        history = self._make_history(count=FALLBACK_THRESHOLD, rating=RATING_DOWN)
        history.extend(self._make_history(count=FALLBACK_WINDOW_SIZE, rating=RATING_UP))
        state = {"feedback_history": history}
        self.assertEqual(should_fallback(state), ROUTE_STANDARD_RAG)

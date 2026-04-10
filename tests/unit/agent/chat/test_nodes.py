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
    def test_should_fallback_no_history(self):
        state = {"feedback_history": []}
        self.assertEqual(should_fallback(state), ROUTE_STANDARD_RAG)

    def test_should_fallback_under_threshold(self):
        # 1 under the threshold should route to standard RAG
        downs = [{"rating": RATING_DOWN}] * (FALLBACK_THRESHOLD - 1)
        state = {"feedback_history": downs}
        self.assertEqual(should_fallback(state), ROUTE_STANDARD_RAG)

    def test_should_fallback_reach_threshold(self):
        # exactly the threshold should route to fallback search
        downs = [{"rating": RATING_DOWN}] * FALLBACK_THRESHOLD
        state = {"feedback_history": downs}
        self.assertEqual(should_fallback(state), ROUTE_FALLBACK_SEARCH)

    def test_should_fallback_exceed_threshold(self):
        # more than the threshold (e.g., threshold + 1) should also route to fallback, checking against == vs >= error
        downs = [{"rating": RATING_DOWN}] * (FALLBACK_THRESHOLD + 1)
        state = {"feedback_history": downs}
        self.assertEqual(should_fallback(state), ROUTE_FALLBACK_SEARCH)

    def test_should_fallback_mixed_recent(self):
        # Window size of feedback containing exactly threshold downs at the end
        history = [{"rating": RATING_UP}] * (FALLBACK_WINDOW_SIZE - FALLBACK_THRESHOLD)
        history.extend([{"rating": RATING_DOWN}] * FALLBACK_THRESHOLD)
        state = {"feedback_history": history}
        self.assertEqual(should_fallback(state), ROUTE_FALLBACK_SEARCH)

    def test_should_fallback_old_downs(self):
        # downs that are older than the window size should be ignored.
        # we put THRESHOLD downs at the very beginning (oldest), and UP for the entire window
        history = [{"rating": RATING_DOWN}] * FALLBACK_THRESHOLD
        history.extend([{"rating": RATING_UP}] * FALLBACK_WINDOW_SIZE)
        state = {"feedback_history": history}
        self.assertEqual(should_fallback(state), ROUTE_STANDARD_RAG)

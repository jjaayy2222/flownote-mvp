# tests/unit/agent/chat/test_nodes.py

import unittest
from backend.agent.chat.nodes import (
    should_fallback,
    ROUTE_FALLBACK_SEARCH,
    ROUTE_STANDARD_RAG,
)
from backend.api.models.shared import RATING_DOWN, RATING_UP


class TestChatNodes(unittest.TestCase):
    def test_should_fallback_no_history(self):
        state = {"feedback_history": []}
        self.assertEqual(should_fallback(state), ROUTE_STANDARD_RAG)

    def test_should_fallback_one_down(self):
        state = {"feedback_history": [{"rating": RATING_DOWN}]}
        self.assertEqual(should_fallback(state), ROUTE_STANDARD_RAG)

    def test_should_fallback_two_downs(self):
        state = {"feedback_history": [{"rating": RATING_DOWN}, {"rating": RATING_DOWN}]}
        self.assertEqual(should_fallback(state), ROUTE_FALLBACK_SEARCH)

    def test_should_fallback_mixed_recent(self):
        # 3 recent items, 2 downs
        state = {
            "feedback_history": [
                {"rating": RATING_UP},
                {"rating": RATING_DOWN},
                {"rating": RATING_DOWN},
            ]
        }
        self.assertEqual(should_fallback(state), ROUTE_FALLBACK_SEARCH)

    def test_should_fallback_old_downs(self):
        # only the last 3 items are considered. Here we have 4 items:
        # the 2 downs are older than the top 3 items -> [DOWN, DOWN, UP, UP] -> last 3 are [DOWN, UP, UP]
        # so negative count = 1 < 2 -> should return STANDARD_RAG
        state = {
            "feedback_history": [
                {"rating": RATING_DOWN},
                {"rating": RATING_DOWN},
                {"rating": RATING_UP},
                {"rating": RATING_UP},
            ]
        }
        self.assertEqual(should_fallback(state), ROUTE_STANDARD_RAG)



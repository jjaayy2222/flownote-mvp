# tests/e2e/test_fallback_e2e.py

import asyncio
from backend.agent.chat.nodes import router_edge, should_fallback
from backend.api.models.shared import RATING_DOWN


def test_e2e_routing():
    # Thumbs Down 시나리오 재현
    print("Running E2E Routing Simulation for Thumbs Down Scenario...")

    # 사용자 초기 상태 (싫어요 2번 연속)
    from langchain_core.messages import HumanMessage
    mock_state = {
        "messages": [HumanMessage(content="제대로 된 답변 좀 줘")],
        "feedback_history": [
            {"rating": RATING_DOWN, "message_id": "msg-1"},
            {"rating": RATING_DOWN, "message_id": "msg-2"},
        ],
    }

    # 라우팅 결과 확인
    selected_route = router_edge(mock_state)

    assert (
        selected_route == "fallback_search"
    ), f"Expected fallback_search, got {selected_route}"
    print(f"✅ Success! Routed to: {selected_route}")


if __name__ == "__main__":
    test_e2e_routing()

# tests/intergration/test_diff_viewer_flown.py

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from tests.test_utils import validate_pydantic_error_structure

client = TestClient(app)

# Shared Constant
MOCK_CONFLICT_ID = "mock-conflict-123"


def test_get_diff_not_found():
    """
    GET /diff with a non-existent conflict_id returns 404.

    The JSONL store has no record for this ID, so the endpoint
    must return 404 — not 200 with empty content.
    This verifies Fail-Fast behaviour introduced in the 1차 개선 commit.
    """
    response = client.get(f"/api/sync/conflicts/{MOCK_CONFLICT_ID}/diff")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


@pytest.mark.parametrize(
    "method, expected_status",
    [
        ("keep_local", 404),  # conflict not in JSONL → 404 before resolution
        ("keep_remote", 404),
        ("keep_both", 404),
        ("invalid_method", 422),  # validation error fires before lookup
    ],
)
def test_resolve_conflict_scenarios(method, expected_status):
    """
    Verify POST /resolve status codes for each resolution method.

    - Valid methods with a non-existent conflict_id → 404
    - Invalid method string → 422 (Pydantic validation, before any lookup)
    Uses ``params`` for safe query-parameter encoding.
    """
    response = client.post(
        f"/api/sync/conflicts/{MOCK_CONFLICT_ID}/resolve",
        params={"resolution_method": method},
    )

    assert response.status_code == expected_status

    if expected_status == 422:
        # Pydantic validation error structure check
        assert response.status_code == 422
        validate_pydantic_error_structure(
            response.json(), ("query", "resolution_method")
        )

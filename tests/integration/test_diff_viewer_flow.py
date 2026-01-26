# tests/intergration/test_diff_viewer_flown.py

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

# Shared Constant
MOCK_CONFLICT_ID = "mock-conflict-123"


def validate_422_error(response, expected_loc: tuple):
    """
    Helper function to validate FastAPI 422 Validation Error structure.
    Checks if the response contains proper validation error details
    pointing to the expected location (e.g., query param name).
    """
    error_body = response.json()
    assert "detail" in error_body, "Error response missing 'detail' field"

    detail = error_body["detail"]
    assert isinstance(detail, list), "'detail' should be a list"
    assert len(detail) > 0, "'detail' list is empty"

    # Validate structure of ALL error items to prevent KeyError later
    # This ensures every item is a dict and has the 'loc' key
    assert all(
        isinstance(e, dict) and "loc" in e for e in detail
    ), "All error items must be dicts with a 'loc' field"

    # Verify exact location match
    # Pydantic validation errors return location as a list
    error_locs = [tuple(e["loc"]) for e in detail]
    assert (
        expected_loc in error_locs
    ), f"Expected error at {expected_loc}, found locations: {error_locs}"


def test_get_diff_schema():
    """
    Verify GET /diff response schema including nested fields.
    Ensures that the backend provides all necessary data fields
    expected by the frontend ConflictDiffViewer.
    """
    response = client.get(f"/api/sync/conflicts/{MOCK_CONFLICT_ID}/diff")
    assert response.status_code == 200

    data = response.json()
    assert data["conflict_id"] == MOCK_CONFLICT_ID
    assert "local_content" in data
    assert "remote_content" in data

    # Deep validation of diff structure
    diff = data["diff"]
    assert "unified" in diff
    assert isinstance(diff["unified"], str)
    assert "html" in diff
    assert isinstance(diff["html"], str)

    # Validate stats structure
    stats = diff["stats"]
    assert "additions" in stats
    assert isinstance(stats["additions"], int)
    assert "deletions" in stats
    assert isinstance(stats["deletions"], int)


@pytest.mark.parametrize(
    "method, expected_status",
    [
        ("keep_local", 200),
        ("keep_remote", 200),
        ("keep_both", 200),
        ("invalid_method", 422),
    ],
)
def test_resolve_conflict_scenarios(method, expected_status):
    """
    Verify POST /resolve with various resolution methods.
    Uses parametrization to cover all valid options and an invalid case.
    Also uses `params` for safe query parameter encoding.
    """
    # Use 'params' argument for safe URL encoding instead of string interpolation
    response = client.post(
        f"/api/sync/conflicts/{MOCK_CONFLICT_ID}/resolve",
        params={"resolution_method": method},
    )

    assert response.status_code == expected_status

    if expected_status == 200:
        result = response.json()
        assert result["status"] == "resolved"
        assert result["method"] == method
        assert result["conflict_id"] == MOCK_CONFLICT_ID
    elif expected_status == 422:
        # Use helper function to validate error structure robustly
        validate_422_error(response, ("query", "resolution_method"))

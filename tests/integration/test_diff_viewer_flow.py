# tests/integration/test_diff_viewer_flow.py

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_get_diff_schema():
    """
    Verify GET /diff response schema including nested fields.
    Ensures that the backend provides all necessary data fields
    expected by the frontend ConflictDiffViewer.
    """
    conflict_id = "mock-conflict-123"
    response = client.get(f"/api/sync/conflicts/{conflict_id}/diff")
    assert response.status_code == 200

    data = response.json()
    assert data["conflict_id"] == conflict_id
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
    conflict_id = "mock-conflict-123"

    # Use 'params' argument for safe URL encoding instead of string interpolation
    response = client.post(
        f"/api/sync/conflicts/{conflict_id}/resolve",
        params={"resolution_method": method},
    )

    assert response.status_code == expected_status

    if expected_status == 200:
        result = response.json()
        assert result["status"] == "resolved"
        assert result["method"] == method
        assert result["conflict_id"] == conflict_id

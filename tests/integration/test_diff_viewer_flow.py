# tests/integration/test_diff_viewer_flow.py

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_diff_viewer_flow():
    """
    Simulate the end-to-end flow for the Diff Viewer feature.
    Since the backend currently uses mock data, this test verifies
    API connectivity, parameter handling, and response schemas.
    """

    conflict_id = "mock-conflict-123"

    # 1. Get Diff Data
    # Verify that the diff endpoint returns the correct structure
    response = client.get(f"/api/sync/conflicts/{conflict_id}/diff")
    assert response.status_code == 200

    data = response.json()
    assert data["conflict_id"] == conflict_id
    assert "local_content" in data
    assert "remote_content" in data
    assert "diff" in data
    assert "stats" in data["diff"]
    assert "unified" in data["diff"]
    assert "html" in data["diff"]

    # 2. Resolve Conflict (Keep Local)
    # Verify resolution API accepts query parameters correctly
    response = client.post(
        f"/api/sync/conflicts/{conflict_id}/resolve?resolution_method=keep_local"
    )
    assert response.status_code == 200

    result = response.json()
    assert result["status"] == "resolved"
    assert result["method"] == "keep_local"
    assert result["conflict_id"] == conflict_id

    # 3. Resolve Conflict (Keep Remote)
    response = client.post(
        f"/api/sync/conflicts/{conflict_id}/resolve?resolution_method=keep_remote"
    )
    assert response.status_code == 200
    assert response.json()["method"] == "keep_remote"

    # 4. Resolve Conflict (Keep Both)
    response = client.post(
        f"/api/sync/conflicts/{conflict_id}/resolve?resolution_method=keep_both"
    )
    assert response.status_code == 200
    assert response.json()["method"] == "keep_both"

    # 5. Invalid Resolution Method
    # Verify validation (Enum check)
    response = client.post(
        f"/api/sync/conflicts/{conflict_id}/resolve?resolution_method=invalid_method"
    )
    assert response.status_code == 422  # Validation Error

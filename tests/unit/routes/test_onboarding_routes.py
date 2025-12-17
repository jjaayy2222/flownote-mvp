import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from backend.main import app

client = TestClient(app)

@pytest.fixture
def mock_onboarding_service():
    with patch("backend.routes.onboarding_routes.onboarding_service") as mock:
        yield mock

def test_step1_create_user(mock_onboarding_service):
    """POST /onboarding/step1 테스트"""
    # Mock 설정
    mock_result = {
        "status": "success",
        "user_id": "user_123",
        "occupation": "Developer",
        "name": "Test User"
    }
    mock_onboarding_service.create_user.return_value = mock_result

    # 요청
    payload = {"name": "Test User", "occupation": "Developer"}
    response = client.post("/onboarding/step1", json=payload)

    # 검증
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user_123"
    assert "next_step" in data
    
    mock_onboarding_service.create_user.assert_called_once_with(
        occupation="Developer", name="Test User"
    )

def test_suggest_areas(mock_onboarding_service):
    """GET /onboarding/suggest-areas 테스트"""
    # Mock 설정
    mock_result = {
        "status": "success",
        "suggested_areas": ["Area1", "Area2"]
    }
    mock_onboarding_service.suggest_areas.return_value = mock_result

    # 요청
    params = {"user_id": "user_123", "occupation": "Developer"}
    response = client.get("/onboarding/suggest-areas", params=params)

    # 검증
    assert response.status_code == 200
    assert response.json()["suggested_areas"] == ["Area1", "Area2"]

def test_save_context(mock_onboarding_service):
    """POST /onboarding/save-context 테스트"""
    # Mock 설정
    mock_result = {
        "status": "success",
        "message": "Saved"
    }
    mock_onboarding_service.save_user_context.return_value = mock_result

    # 요청
    payload = {"user_id": "user_123", "selected_areas": ["Area1"]}
    response = client.post("/onboarding/save-context", json=payload)

    # 검증
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_get_status_success(mock_onboarding_service):
    """GET /onboarding/status/{user_id} 성공 테스트"""
    mock_result = {
        "status": "success",
        "is_completed": True
    }
    mock_onboarding_service.get_user_status.return_value = mock_result

    response = client.get("/onboarding/status/user_123")
    
    assert response.status_code == 200
    assert response.json()["is_completed"] is True

def test_get_status_not_found(mock_onboarding_service):
    """GET /onboarding/status/{user_id} 실패 테스트"""
    mock_result = {
        "status": "error",
        "message": "User not found"
    }
    mock_onboarding_service.get_user_status.return_value = mock_result

    response = client.get("/onboarding/status/unknown_user")
    
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"

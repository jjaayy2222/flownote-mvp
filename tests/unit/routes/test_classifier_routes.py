import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from backend.main import app
from backend.models import ClassifyResponse

client = TestClient(app)

@pytest.fixture
def mock_classification_service():
    with patch("backend.routes.classifier_routes.classification_service") as mock:
        yield mock

def test_classify_text_success(mock_classification_service):
    """POST /classifier/classify 성공 테스트"""
    # Mock 설정
    mock_response = ClassifyResponse(
        category="Projects",
        confidence=0.9,
        snapshot_id="snap_123",
        keyword_tags=["test"],
        reasoning="Test reasoning",
        user_context_matched=True,
        context_injected=False
    )
    mock_classification_service.classify = AsyncMock(return_value=mock_response)

    # 요청
    payload = {
        "text": "프로젝트 마감일 확인",
        "user_id": "user_001"
    }
    response = client.post("/classifier/classify", json=payload)

    # 검증
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "Projects"
    assert data["confidence"] == 0.9
    
    # Service 호출 확인
    mock_classification_service.classify.assert_called_once()

def test_classify_text_error(mock_classification_service):
    """POST /classifier/classify 에러 처리 테스트"""
    # Mock 설정 (예외 발생)
    mock_classification_service.classify = AsyncMock(side_effect=Exception("Service Error"))

    # 요청
    payload = {"text": "Error case"}
    response = client.post("/classifier/classify", json=payload)

    # 검증
    assert response.status_code == 500
    assert "분류 실패" in response.json()["detail"]

def test_classify_file_success(mock_classification_service):
    """POST /classifier/file 성공 테스트"""
    # Mock 설정
    mock_response = ClassifyResponse(
        category="Resources",
        confidence=0.8,
        snapshot_id="snap_file_123",
        keyword_tags=["file"],
        reasoning="File reasoning",
        user_context_matched=False,
        context_injected=False
    )
    mock_classification_service.classify = AsyncMock(return_value=mock_response)

    # 파일 업로드 요청
    files = {"file": ("test.txt", b"File content", "text/plain")}
    data = {"user_id": "user_001", "occupation": "Developer"}
    
    response = client.post("/classifier/file", files=files, data=data)

    # 검증
    assert response.status_code == 200
    data = response.json()
    assert data["category"] == "Resources"
    
    # Service 호출 확인
    mock_classification_service.classify.assert_called_once()

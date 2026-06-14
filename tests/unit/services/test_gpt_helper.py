# tests/unit/services/test_gpt_helper.py

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.services.gpt_helper import GPT4oHelper


@pytest.fixture
def gpt_helper():
    return GPT4oHelper()


def test_suggest_areas_success(gpt_helper):
    """
    suggest_areas 정상 동작 테스트
    """
    # Arrange
    mock_response = json.dumps({"areas": ["Area1", "Area2", "Area3"]})

    with patch.object(gpt_helper, "_call", return_value=mock_response) as mock_call:
        # Act
        result = gpt_helper.suggest_areas("Developer", count=3)

        # Assert
        assert result["status"] == "success"
        assert len(result["areas"]) == 3
        assert "Area1" in result["areas"]
        mock_call.assert_called_once()


def test_suggest_areas_json_error_fallback(gpt_helper):
    """
    suggest_areas JSON 파싱 에러 시 Fallback 동작 테스트
    """
    # Arrange
    mock_response = "Invalid JSON"

    with patch.object(gpt_helper, "_call", return_value=mock_response):
        # Act
        result = gpt_helper.suggest_areas("개발자", count=5)

        # Assert
        assert result["status"] == "success"  # Fallback은 success로 처리됨
        assert len(result["areas"]) == 10  # 개발자는 fallback_map에 10개 정의됨
        assert "코드 리뷰" in result["areas"]  # Developer Fallback 데이터 확인


def test_generate_keywords_success(gpt_helper):
    """
    generate_keywords 정상 동작 테스트
    """
    # Arrange
    mock_response = json.dumps({"Area1": ["Key1", "Key2"], "Area2": ["Key3", "Key4"]})

    with patch.object(gpt_helper, "_call", return_value=mock_response):
        # Act
        result = gpt_helper.generate_keywords("Developer", ["Area1", "Area2"])

        # Assert
        assert "Area1" in result
        assert "Key1" in result["Area1"]


def test_classify_text_success(gpt_helper):
    """
    classify_text 정상 동작 테스트
    """
    # Arrange
    mock_response = json.dumps(
        {"category": "Projects", "confidence": 0.95, "reasoning": "Test Reasoning"}
    )

    with patch.object(gpt_helper, "_call", return_value=mock_response):
        # Act
        result = gpt_helper.classify_text("Test Text", ["Projects", "Areas"])

        # Assert
        assert result["status"] == "success"
        assert result["category"] == "Projects"
        assert result["confidence"] == 0.95


def test_classify_text_error(gpt_helper):
    """
    classify_text 에러 발생 시 Fallback 테스트
    """
    # Arrange
    with patch.object(gpt_helper, "_call", side_effect=Exception("API Error")):
        # Act
        result = gpt_helper.classify_text("Test Text", ["Projects", "Areas"])

        # Assert
        assert result["status"] == "error"
        assert result["category"] == "Projects"  # 첫 번째 카테고리 반환
        assert result["confidence"] == 0.5

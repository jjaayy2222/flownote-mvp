# tests/unit/services/test_parallel_processor.py

import pytest
from unittest.mock import patch
from backend.services.parallel_processor import ParallelClassifier


def test_classify_parallel_success():
    """
    ParallelClassifier.classify_parallel 정상 동작 테스트
    """
    # Arrange
    text = "Test Text"
    metadata = {"filename": "test.txt"}

    mock_text_result = {"category": "Projects", "confidence": 0.9}
    mock_meta_result = {"category": "Resources", "confidence": 0.8}

    with patch(
        "backend.services.parallel_processor.classify_with_langchain",
        return_value=mock_text_result,
    ) as mock_langchain:
        with patch(
            "backend.services.parallel_processor.classify_with_metadata",
            return_value=mock_meta_result,
        ) as mock_metadata:

            # Act
            result = ParallelClassifier.classify_parallel(text, metadata)

            # Assert
            assert result["status"] == "success"
            assert result["text_result"] == mock_text_result
            assert result["metadata_result"] == mock_meta_result
            assert "execution_time" in result

            mock_langchain.assert_called_once_with(text)
            mock_metadata.assert_called_once_with(metadata)


def test_classify_parallel_error():
    """
    ParallelClassifier.classify_parallel 에러 발생 시 처리 테스트
    """
    # Arrange
    text = "Test Text"
    metadata = {"filename": "test.txt"}

    with patch(
        "backend.services.parallel_processor.classify_with_langchain",
        side_effect=Exception("Processing Error"),
    ):
        # Act
        result = ParallelClassifier.classify_parallel(text, metadata)

        # Assert
        assert result["status"] == "error"
        assert "Processing Error" in result["message"]

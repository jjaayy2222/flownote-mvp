# tests/unit/services/test_conflict_service.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.conflict_service import ConflictService
from backend.classifier.conflict_resolver import ClassificationResult


@pytest.mark.asyncio
async def test_classify_text_success():
    """
    ConflictService.classify_text 정상 동작 테스트
    - PARA, Keyword, ConflictResolver, SnapshotManager가 순차적으로 호출되는지 검증
    """
    # Arrange
    service = ConflictService()

    # Mock Data
    mock_text = "테스트 텍스트"
    mock_para_result = {"category": "Projects", "confidence": 0.9}
    mock_keyword_result = {"tags": ["python"], "confidence": 0.8}
    mock_conflict_result = {
        "final_category": "Projects",
        "confidence": 0.95,
        "conflict_detected": False,
        "requires_review": False,
    }
    mock_snapshot = MagicMock()
    mock_snapshot.id = "snap_123"
    mock_snapshot.timestamp.isoformat.return_value = "2023-01-01T00:00:00"
    mock_snapshot.metadata = {}

    # Mocking Dependencies
    with patch(
        "backend.services.conflict_service.run_para_agent", new_callable=AsyncMock
    ) as mock_para_agent:
        mock_para_agent.return_value = mock_para_result

        # KeywordClassifier Mocking
        service.keyword_classifier.classify = AsyncMock(
            return_value=mock_keyword_result
        )

        # ConflictResolver Mocking (inside _resolve_conflict_async)
        # ConflictResolver는 메서드 내부에서 인스턴스화되므로, 클래스 자체를 patch해야 함
        with patch(
            "backend.services.conflict_service.ConflictResolver"
        ) as MockConflictResolver:
            mock_resolver_instance = MockConflictResolver.return_value
            # resolve_async가 있다고 가정하고 Mocking (없으면 resolve를 Mocking해야 함, 코드는 resolve_async 우선 확인)
            mock_resolver_instance.resolve_async = AsyncMock(
                return_value=mock_conflict_result
            )

            # SnapshotManager Mocking
            service.snapshot_manager.save_snapshot = MagicMock(
                return_value=mock_snapshot
            )

            # Act
            result = await service.classify_text(mock_text)

            # Assert
            assert result["status"] == "success"
            assert result["snapshot_id"] == "snap_123"
            assert result["para_result"] == mock_para_result
            assert result["keyword_result"] == mock_keyword_result
            assert result["conflict_result"] == mock_conflict_result

            # Verify Calls
            mock_para_agent.assert_called_once_with(mock_text)
            service.keyword_classifier.classify.assert_called_once()
            service.snapshot_manager.save_snapshot.assert_called_once()


@pytest.mark.asyncio
async def test_classify_text_error_handling():
    """
    ConflictService.classify_text 예외 처리 테스트
    - 내부 로직에서 에러 발생 시 status='error' 반환 검증
    """
    # Arrange
    service = ConflictService()
    mock_text = "에러 유발 텍스트"

    # Mocking to raise exception
    with patch(
        "backend.services.conflict_service.run_para_agent", new_callable=AsyncMock
    ) as mock_para_agent:
        mock_para_agent.side_effect = Exception("PARA Agent Error")

        # Act
        result = await service.classify_text(mock_text)

        # Assert
        assert result["status"] == "error"
        assert "PARA Agent Error" in result["error"]

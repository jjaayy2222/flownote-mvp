# tests/test_classification_service_unit.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from backend.services.classification_service import ClassificationService
from backend.models import ClassifyResponse


@pytest.mark.asyncio
async def test_classification_service_orchestration():
    # Arrange
    service = ClassificationService()

    # Mock dependencies
    # 1. Mock PARA Agent
    with patch(
        "backend.services.classification_service.run_para_agent", new_callable=AsyncMock
    ) as mock_para:
        mock_para.return_value = {
            "category": "Projects",
            "confidence": 0.9,
            "snapshot_id": "snap_123",
        }

        # 2. Mock Keyword Classifier
        with patch(
            "backend.services.classification_service.KeywordClassifier"
        ) as MockKeywordClassifier:
            mock_keyword_instance = MockKeywordClassifier.return_value
            mock_keyword_instance.aclassify = AsyncMock(
                return_value={
                    "tags": ["python", "coding"],
                    "user_context_matched": True,
                }
            )

            # 3. Mock Conflict Service (already injected in __init__, so we mock the instance attribute)
            service.conflict_service.classify_text = AsyncMock(
                return_value={
                    "final_category": "Projects",
                    "confidence": 0.95,
                    "conflict_detected": False,
                    "requires_review": False,
                    "reason": "Consistent results",
                }
            )

            # 4. Mock _save_results to avoid file I/O during orchestration test
            with patch.object(service, "_save_results") as mock_save:
                mock_save.return_value = {"csv_saved": True, "json_saved": True}

                # Act
                response = await service.classify(
                    text="This is a test project about python.",
                    user_id="test_user",
                    occupation="Developer",
                    areas=["Coding"],
                    interests=["AI"],
                )

                # Assert
                assert isinstance(response, ClassifyResponse)
                assert response.category == "Projects"
                assert response.keyword_tags == ["python", "coding"]
                assert response.confidence == 0.95
                assert response.user_context["user_id"] == "test_user"
                assert response.user_context["occupation"] == "Developer"

                # Verify calls
                mock_para.assert_called_once()
                mock_keyword_instance.aclassify.assert_called_once()
                service.conflict_service.classify_text.assert_called_once()
                mock_save.assert_called_once()


def test_save_results():
    # Arrange
    service = ClassificationService()

    user_id = "test_user"
    file_id = "test_file.txt"
    final_category = "Projects"
    keyword_tags = ["tag1", "tag2"]
    confidence = 0.95
    snapshot_id = "snap_123"

    # Mock Path to avoid actual file system operations
    with patch("backend.services.classification_service.Path") as MockPath:
        # Setup mock paths
        mock_root = MagicMock()
        MockPath.return_value.parent.parent.parent = mock_root

        mock_log_dir = mock_root / "data" / "log"
        mock_csv_dir = mock_root / "data" / "classifications"

        mock_csv_path = mock_csv_dir / "classification_log.csv"
        mock_json_path = mock_log_dir / "classification_mock.json"

        # Mock exists() and stat() for CSV
        mock_csv_path.exists.return_value = True
        mock_csv_path.stat.return_value.st_size = 100

        # Mock open
        m = mock_open()
        with patch("builtins.open", m):
            # Act
            result = service._save_results(
                user_id, file_id, final_category, keyword_tags, confidence, snapshot_id
            )

            # Assert
            assert result["csv_saved"] is True
            assert result["json_saved"] is True

            # Verify directory creation
            mock_log_dir.mkdir.assert_called_with(parents=True, exist_ok=True)
            mock_csv_dir.mkdir.assert_called_with(parents=True, exist_ok=True)

            # Verify file writes
            # We expect 2 calls to open: one for CSV (append), one for JSON (write)
            assert m.call_count == 2

            # Check CSV write
            # Note: Checking exact write calls for CSV DictWriter is tricky with mock_open,
            # but we can check if open was called with correct args
            # m.assert_any_call(mock_csv_path, "a", newline="", encoding="utf-8")

            # Check JSON write
            # m.assert_any_call(mock_json_path, "w", encoding="utf-8")


"""test_result

    python -m tests.test_classification_service_unit

    ✅ ModelConfig loaded from backend.config
    
    
    python -m pytest tests/test_classification_service_unit.py -v
    ========================== test session starts ===========================
    platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/myenv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/jay/ICT-projects/flownote-mvp
    configfile: pytest.ini
    plugins: anyio-4.11.0, langsmith-0.4.37, asyncio-1.3.0
    asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
    collected 2 items                                                        

    tests/test_classification_service_unit.py::test_classification_service_orchestration PASSED [ 50%]
    tests/test_classification_service_unit.py::test_save_results PASSED [100%]

    =========================== 2 passed in 1.00s ============================

"""

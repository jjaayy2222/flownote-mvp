# tests/integration/test_hybrid_flow.py

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.classification_service import ClassificationService
from backend.services.rule_engine import RuleResult


@pytest.mark.asyncio
async def test_hybrid_flow_end_to_end_rule_match():
    """
    [Integration] ClassificationService: Rule Hit Scenario

    Verifies that when the rule engine returns a matching rule, the
    classification result uses the rule's category and confidence,
    triggers the save logic, and does NOT invoke the AI classifier.

    Note: This test focuses on the final routing and persistence trigger,
    not the internal conflict resolution details or actual file I/O.
    """
    service = ClassificationService()

    # 1. Patch RuleEngine to return match
    # 2. Patch _save_results to prevent disk I/O during test
    with patch(
        "backend.services.rule_engine.RuleEngine.evaluate"
    ) as mock_rule_eval, patch.object(service, "_save_results") as mock_save:

        mock_rule_eval.return_value = RuleResult(
            category="Projects", confidence=0.95, matched_rule="test_integration_rule"
        )
        mock_save.return_value = {"csv_saved": True, "json_saved": True}

        # Mock AI to ensure it's NOT called
        service.hybrid_classifier.ai_classifier.classify = AsyncMock()

        # Act
        text = "This is a detailed project plan regarding integration testing."
        response = await service.classify(
            text=text, user_id="user_int_rule", areas=["DevOps"]
        )

        # Assert
        assert response.category == "Projects"
        assert response.confidence >= 0.95

        # Verify wiring
        service.hybrid_classifier.ai_classifier.classify.assert_not_called()
        mock_save.assert_called_once()
        assert response.log_info.get("csv_saved") is True


@pytest.mark.asyncio
async def test_hybrid_flow_end_to_end_ai_fallback():
    """
    [Integration] ClassificationService: Rule Miss -> AI Fallback Scenario

    Verifies that when the rule engine finds no match, the system correctly
    falls back to the AI classifier and returns its result.
    """
    service = ClassificationService()

    # Patch RuleEngine (Miss) and _save_results (No I/O)
    with patch(
        "backend.services.rule_engine.RuleEngine.evaluate", return_value=None
    ), patch.object(service, "_save_results") as mock_save:

        mock_save.return_value = {"csv_saved": True, "json_saved": True}

        # HybridClassifier expects AI to return dict with category, confidence, method
        service.hybrid_classifier.ai_classifier.classify = AsyncMock(
            return_value={
                "category": "Areas",
                "confidence": 0.88,
                "reasoning": "Semantic match for Areas",
                "method": "ai",
            }
        )

        # Act
        text = "Maintain monthly server health checks."
        response = await service.classify(
            text=text, user_id="user_int_ai", areas=["SysAdmin"]
        )

        # Assert
        assert response.category == "Areas"

        # Verify wiring
        service.hybrid_classifier.ai_classifier.classify.assert_called_once()
        mock_save.assert_called_once()

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
    - Context Build -> Hybrid(Rule) -> Keywords -> Conflict -> Save
    """
    # Initialize Service
    service = ClassificationService()

    # Patch RuleEngine to return a match
    # Note: We are patching the class method used by the instance inside service
    with patch("backend.services.rule_engine.RuleEngine.evaluate") as mock_rule_eval:
        mock_rule_eval.return_value = RuleResult(
            category="Projects", confidence=0.95, matched_rule="test_integration_rule"
        )

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
        assert response.log_info.get("csv_saved") is True

        # Verify AI was NOT called
        service.hybrid_classifier.ai_classifier.classify.assert_not_called()


@pytest.mark.asyncio
async def test_hybrid_flow_end_to_end_ai_fallback():
    """
    [Integration] ClassificationService: Rule Miss -> AI Fallback Scenario
    """
    service = ClassificationService()

    # 1. Rule Miss
    with patch("backend.services.rule_engine.RuleEngine.evaluate", return_value=None):

        # 2. AI Hit
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
        assert response.log_info.get("json_saved") is True

        # Verify AI WAS called
        service.hybrid_classifier.ai_classifier.classify.assert_called_once()

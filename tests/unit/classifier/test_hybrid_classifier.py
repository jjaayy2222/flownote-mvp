# tests/unit/classifier/test_hybrid_classifier.py

import pytest
from unittest.mock import MagicMock, AsyncMock
from backend.classifier.hybrid_classifier import HybridClassifier
from backend.services.rule_engine import RuleEngine, RuleResult
from backend.classifier.ai_classifier import AIClassifier


@pytest.fixture
def mock_rule_engine():
    return MagicMock(spec=RuleEngine)


@pytest.fixture
def mock_ai_classifier():
    classifier = MagicMock(spec=AIClassifier)
    # classify는 async 메서드이므로 AsyncMock 사용
    classifier.classify = AsyncMock()
    return classifier


@pytest.fixture
def hybrid_classifier(mock_rule_engine, mock_ai_classifier):
    return HybridClassifier(
        rule_engine=mock_rule_engine,
        ai_classifier=mock_ai_classifier,
        rule_threshold=0.8,
    )


def test_init_threshold_validation(mock_rule_engine, mock_ai_classifier):
    """threshold 유효성 및 경계값 검증 테스트"""
    # Invalid cases
    with pytest.raises(ValueError):
        HybridClassifier(mock_rule_engine, mock_ai_classifier, rule_threshold=1.5)

    with pytest.raises(ValueError):
        HybridClassifier(mock_rule_engine, mock_ai_classifier, rule_threshold=-0.1)

    # Valid boundary cases (should not raise)
    hc_zero = HybridClassifier(mock_rule_engine, mock_ai_classifier, rule_threshold=0.0)
    assert hc_zero.rule_threshold == 0.0

    hc_one = HybridClassifier(mock_rule_engine, mock_ai_classifier, rule_threshold=1.0)
    assert hc_one.rule_threshold == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "threshold, confidence, expected_method",
    [
        # Standard Cases
        (0.8, 0.9, "rule"),  # Conf > Threshold -> Rule
        (0.8, 0.8, "rule"),  # Conf == Threshold -> Rule (Boundary Inclusive)
        (0.8, 0.79, "ai"),  # Conf < Threshold -> AI
        (0.5, 0.6, "rule"),  # Low Threshold, Rule Hit
        (0.5, 0.4, "ai"),  # Low Threshold, Rule Miss -> AI Fallback
        # Edge Case: Threshold 0.0 (Accept EVERYTHING if rule matches)
        (0.0, 0.0, "rule"),  # Zero confidence is accepted if rule matched
        (0.0, 0.1, "rule"),  # Any confidence is accepted
        # Edge Case: Threshold 1.0 (Strict acceptance)
        (1.0, 1.0, "rule"),  # Only perfect confidence accepted
        (1.0, 0.99, "ai"),  # Near perfect rejected -> AI Fallback
    ],
)
async def test_classify_threshold_logic(
    mock_rule_engine, mock_ai_classifier, threshold, confidence, expected_method
):
    """Threshold와 Confidence 조합에 따른 분류 경로(Rule vs AI) 검증"""

    # Mock Rule Result
    mock_rule_engine.evaluate.return_value = RuleResult(
        category="Projects", confidence=confidence, matched_rule="test_rule"
    )

    # Mock AI Result
    mock_ai_classifier.classify.return_value = {
        "category": "AI-Category",
        "confidence": 0.9,
        "method": "ai",
    }

    classifier = HybridClassifier(
        rule_engine=mock_rule_engine,
        ai_classifier=mock_ai_classifier,
        rule_threshold=threshold,
    )

    result = await classifier.classify("test text")

    assert result["method"] == expected_method

    if expected_method == "rule":
        assert result["category"] == "Projects"
        mock_ai_classifier.classify.assert_not_called()
    else:
        assert result["category"] == "AI-Category"
        mock_ai_classifier.classify.assert_called_once()


@pytest.mark.asyncio
async def test_classify_rule_miss(
    hybrid_classifier, mock_rule_engine, mock_ai_classifier
):
    """RuleEngine 매칭 실패(None) 시 무조건 AI Fallback"""
    mock_rule_engine.evaluate.return_value = None

    mock_ai_classifier.classify.return_value = {
        "category": "Resources",
        "confidence": 0.85,
        "method": "ai",
    }

    result = await hybrid_classifier.classify("ambiguous text")

    assert result["method"] == "ai"
    mock_ai_classifier.classify.assert_called_once()


@pytest.mark.asyncio
async def test_classify_rule_error_resilience(
    hybrid_classifier, mock_rule_engine, mock_ai_classifier
):
    """RuleEngine 에러 발생 시 무시하고 AI로 진행"""
    mock_rule_engine.evaluate.side_effect = Exception("Rule Engine Crash")

    mock_ai_classifier.classify.return_value = {
        "category": "Areas",
        "confidence": 0.8,
        "method": "ai",
    }

    result = await hybrid_classifier.classify("text")

    assert result["method"] == "ai"
    assert "Rule Engine Crash" in hybrid_classifier.last_error


@pytest.mark.asyncio
async def test_classify_empty_text(hybrid_classifier):
    """빈 텍스트 처리"""
    result = await hybrid_classifier.classify("")

    assert result["method"] == "validation_error"

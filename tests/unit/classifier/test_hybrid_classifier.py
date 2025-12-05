import pytest
from unittest.mock import MagicMock, AsyncMock, ANY
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
    "threshold, rule_matches, rule_confidence, expected_method",
    [
        # --- Standard Cases (Rule Matches) ---
        (0.8, True, 0.9, "rule"),  # Conf > Threshold -> Rule
        (0.8, True, 0.8, "rule"),  # Conf == Threshold -> Rule
        (0.8, True, 0.79, "ai"),  # Conf < Threshold -> AI
        # --- Low Threshold Cases (Rule Matches) ---
        (0.5, True, 0.6, "rule"),  # Conf > Threshold -> Rule
        (0.5, True, 0.4, "ai"),  # Conf < Threshold -> AI
        # --- Edge Case: Threshold 0.0 (Accept Match) ---
        (0.0, True, 0.0, "rule"),  # Zero Conf Rule -> Rule
        # --- Edge Case: Rule Miss (ALWAYS AI Fallback) ---
        (0.0, False, 0.0, "ai"),  # No Match at 0.0 -> AI
        (0.5, False, 0.0, "ai"),  # No Match at 0.5 -> AI
        (1.0, False, 0.0, "ai"),  # No Match at 1.0 -> AI
        # --- Edge Case: Threshold 1.0 (Strict) ---
        (1.0, True, 1.0, "rule"),  # Perfect Conf -> Rule
        (1.0, True, 0.99, "ai"),  # Near Perfect -> AI
    ],
)
async def test_classify_threshold_logic(
    mock_rule_engine,
    mock_ai_classifier,
    threshold,
    rule_matches,
    rule_confidence,
    expected_method,
):
    """Threshold, Rule Match 여부, Confidence 조합에 따른 분류 경로 및 Wiring 검증"""

    test_text = "test text"

    # 1. Mock Rule Engine Setup
    if rule_matches:
        mock_rule_engine.evaluate.return_value = RuleResult(
            category="Projects", confidence=rule_confidence, matched_rule="test_rule"
        )
    else:
        mock_rule_engine.evaluate.return_value = None

    # 2. Mock AI Classifier Setup
    mock_ai_classifier.classify.return_value = {
        "category": "AI-Category",
        "confidence": 0.9,
        "method": "ai",
    }

    # 3. Initialize Classifer
    classifier = HybridClassifier(
        rule_engine=mock_rule_engine,
        ai_classifier=mock_ai_classifier,
        rule_threshold=threshold,
    )

    # 4. Execute
    result = await classifier.classify(test_text)

    # 5. Verify Method
    assert result["method"] == expected_method

    # 6. Verify Wiring (Rule Engine)
    # metadata may occur as None or {}, so check flexible
    mock_rule_engine.evaluate.assert_called_once()
    # Check only position arg 0 (test_text) to be robust against metadata default changes
    args, _ = mock_rule_engine.evaluate.call_args
    assert args[0] == test_text

    # 7. Verify Routing & AI Wiring
    if expected_method == "rule":
        assert result["category"] == "Projects"
        mock_ai_classifier.classify.assert_not_called()
    else:
        assert result["category"] == "AI-Category"
        # AI Classifier must be awaited call with exact args (text, context=None)
        mock_ai_classifier.classify.assert_awaited_once_with(test_text, None)


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

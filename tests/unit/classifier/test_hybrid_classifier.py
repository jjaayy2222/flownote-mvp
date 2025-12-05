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


def test_init_invalid_threshold(mock_rule_engine, mock_ai_classifier):
    """threshold 범위 검증 테스트"""
    with pytest.raises(ValueError):
        HybridClassifier(mock_rule_engine, mock_ai_classifier, rule_threshold=1.5)

    with pytest.raises(ValueError):
        HybridClassifier(mock_rule_engine, mock_ai_classifier, rule_threshold=-0.1)


@pytest.mark.asyncio
async def test_hybrid_classifier_respects_configurable_rule_threshold(
    mock_rule_engine, mock_ai_classifier
):
    """설정된 threshold에 따라 동작이 달라지는지 검증"""
    # 동일한 RuleResult (confidence 0.6)
    mock_rule_engine.evaluate.return_value = RuleResult(
        category="Projects", confidence=0.6, matched_rule="project_keyword"
    )

    # AI 응답 설정
    mock_ai_classifier.classify.return_value = {
        "category": "AI-Category",
        "confidence": 0.9,
        "method": "ai",
    }

    # Case 1: 낮은 threshold (0.5) -> Rule Hit
    low_threshold_classifier = HybridClassifier(
        rule_engine=mock_rule_engine,
        ai_classifier=mock_ai_classifier,
        rule_threshold=0.5,
    )
    result_low = await low_threshold_classifier.classify("some text")
    assert result_low["category"] == "Projects"
    assert result_low["method"] == "rule"
    mock_ai_classifier.classify.assert_not_called()

    # Mock 초기화
    mock_ai_classifier.classify.reset_mock()

    # Case 2: 높은 threshold (0.8) -> AI Fallback
    default_threshold_classifier = HybridClassifier(
        rule_engine=mock_rule_engine,
        ai_classifier=mock_ai_classifier,
        rule_threshold=0.8,
    )
    result_default = await default_threshold_classifier.classify("some text")
    assert result_default["category"] == "AI-Category"
    assert result_default["method"] == "ai"
    mock_ai_classifier.classify.assert_called_once()


@pytest.mark.asyncio
async def test_classify_rule_hit(
    hybrid_classifier, mock_rule_engine, mock_ai_classifier
):
    """RuleEngine이 높은 점수로 매칭되면 AI 호출 안 함"""
    # Rule 매칭 성공 설정
    mock_rule_engine.evaluate.return_value = RuleResult(
        category="Projects", confidence=0.9, matched_rule="project_keyword"
    )

    result = await hybrid_classifier.classify("Finalize project plan")

    # 결과 검증
    assert result["category"] == "Projects"
    assert result["confidence"] == 0.9
    assert result["method"] == "rule"
    assert "project_keyword" in result["reasoning"]

    # AIClassifier는 호출되지 않아야 함
    mock_ai_classifier.classify.assert_not_called()


@pytest.mark.asyncio
async def test_classify_rule_threshold_boundary(
    hybrid_classifier, mock_rule_engine, mock_ai_classifier
):
    """RuleEngine confidence가 threshold(0.8)와 같을 때도 Rule path 사용"""
    mock_rule_engine.evaluate.return_value = RuleResult(
        category="Projects", confidence=0.8, matched_rule="deadline_pattern"
    )

    result = await hybrid_classifier.classify("Deadline: 2025-12-31")

    # AI 호출 없이 Rule 결과 반환 확인
    assert result["category"] == "Projects"
    assert result["method"] == "rule"
    mock_ai_classifier.classify.assert_not_called()


@pytest.mark.asyncio
async def test_classify_ai_fallback(
    hybrid_classifier, mock_rule_engine, mock_ai_classifier
):
    """RuleEngine 매칭 실패 시 AI Fallback"""
    # Rule 매칭 실패 (None 또는 낮은 점수)
    mock_rule_engine.evaluate.return_value = None

    # AI 반환값 설정
    mock_ai_classifier.classify.return_value = {
        "category": "Resources",
        "confidence": 0.85,
        "reasoning": "AI reasoning",
        "method": "ai",
    }

    result = await hybrid_classifier.classify("Some ambiguous text")

    # 결과 검증
    assert result["category"] == "Resources"
    assert result["method"] == "ai"

    # AIClassifier가 호출되어야 함
    mock_ai_classifier.classify.assert_called_once()


@pytest.mark.asyncio
async def test_classify_rule_low_confidence(
    hybrid_classifier, mock_rule_engine, mock_ai_classifier
):
    """RuleEngine 점수가 낮으면 AI Fallback"""
    # 점수가 threshold(0.8)보다 낮음 (0.79)
    mock_rule_engine.evaluate.return_value = RuleResult(
        category="Projects", confidence=0.79, matched_rule="possible_project"
    )

    mock_ai_classifier.classify.return_value = {
        "category": "Projects",
        "confidence": 0.9,
        "method": "ai",
    }

    await hybrid_classifier.classify("text")

    # AI 호출되어야 함
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

    assert result["category"] == "Areas"
    assert result["method"] == "ai"

    # 에러가 last_error에 기록되었는지 확인
    assert "Rule Engine Crash" in hybrid_classifier.last_error


@pytest.mark.asyncio
async def test_classify_empty_text(hybrid_classifier):
    """빈 텍스트 처리"""
    result = await hybrid_classifier.classify("")

    # validation_error로 구분되는지 확인
    assert result["method"] == "validation_error"

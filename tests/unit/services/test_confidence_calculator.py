# tests/unit/services/test_confidence_calculator.py

import pytest
from backend.services.confidence_calculator import ConfidenceCalculator

@pytest.fixture
def calculator():
    return ConfidenceCalculator()

def test_calculate_base_score_only(calculator):
    """기본 가중 평균 계산 테스트 (조정 없음)"""
    scores = {
        "rule": 0.8,    # weight 0.25
        "keyword": 0.8, # weight 0.20
        "ai": 0.8,      # weight 0.40
        "user": 0.8     # weight 0.15
    }
    # 모든 점수가 0.8이므로 가중 평균도 0.8이어야 함
    # Agreement Boost가 적용될 수 있으므로 features를 비워두고 확인
    
    result = calculator.calculate(scores, {})
    
    # Agreement Boost(0.15)가 적용되어 0.95가 됨 (0.8 + 0.15)
    assert result.score == pytest.approx(0.95)
    assert result.action == "auto_apply"

def test_calculate_weighted_average(calculator):
    """가중치가 다른 점수들의 평균 계산"""
    scores = {
        "rule": 1.0,    # 0.25 * 1.0 = 0.25
        "ai": 0.5,      # 0.40 * 0.5 = 0.20
    }
    # 총 가중치: 0.65
    # 가중 합: 0.45
    # 예상 기본 점수: 0.45 / 0.65 ≈ 0.692
    
    # Agreement 조건: 1.0과 0.5는 차이가 0.5로 큼 -> Disagreement Penalty?
    # 하지만 0.5는 threshold(0.6) 미만이므로 valid_scores에 포함되지 않음
    # 따라서 Agreement/Disagreement 로직 타지 않음
    
    result = calculator.calculate(scores)
    expected_base = round(0.45 / 0.65, 3)
    assert result.details["base_score"] == expected_base

def test_agreement_boost(calculator):
    """분류기 간 동의 시 부스트 적용"""
    scores = {
        "ai": 0.9,
        "rule": 0.85
    }
    # 둘 다 0.6 이상이고 차이가 0.05 (< 0.15) -> Agreement Boost (+0.15)
    
    result = calculator.calculate(scores)
    
    # "Agreement Boost"가 이유에 포함되어야 함
    assert any("Agreement Boost" in r for r in result.reasons)
    assert result.score > result.details["base_score"]

def test_disagreement_penalty(calculator):
    """분류기 간 불일치 시 페널티 적용"""
    scores = {
        "ai": 0.9,
        "rule": 0.4  # 0.4는 threshold 미만이므로 무시됨 -> Disagreement 발생 안 함
    }
    # Disagreement를 유발하려면 둘 다 threshold(0.6) 이상이어야 함
    scores_valid = {
        "ai": 0.95,
        "rule": 0.60
    }
    # 차이 0.35 > 0.3 (0.15 * 2) -> Disagreement Penalty (-0.20)
    
    result = calculator.calculate(scores_valid)
    
    assert any("Disagreement Penalty" in r for r in result.reasons)
    assert result.score < result.details["base_score"]

def test_feature_adjustments(calculator):
    """파일 특성에 따른 점수 조정"""
    scores = {"ai": 0.7} # Base score 0.7
    features = {
        "access_frequency": 0.8,  # High freq boost (+0.10)
        "days_since_edit": 3,     # Recent edit boost (+0.05)
        "text_length": 100        # Normal length
    }
    
    result = calculator.calculate(scores, features)
    
    # Base 0.7 + 0.10 + 0.05 = 0.85
    assert result.score == pytest.approx(0.85)
    assert any("High Frequency Boost" in r for r in result.reasons)
    assert any("Recent Edit Boost" in r for r in result.reasons)

def test_low_info_penalty(calculator):
    """정보 부족(짧은 텍스트) 페널티"""
    scores = {"ai": 0.7}
    features = {
        "text_length": 10  # Low info penalty (-0.10)
    }
    
    result = calculator.calculate(scores, features)
    
    # Base 0.7 - 0.10 = 0.60
    assert result.score == pytest.approx(0.60)
    assert any("Low Info Penalty" in r for r in result.reasons)

def test_score_clamping(calculator):
    """점수가 0.0 ~ 1.0 범위를 벗어나지 않도록 클램핑"""
    # 1.0 초과 케이스
    scores_high = {"ai": 1.0, "rule": 1.0} # Base 1.0 + Agreement 0.15 = 1.15 -> 1.0
    result_high = calculator.calculate(scores_high)
    assert result_high.score == 1.0
    
    # 0.0 미만 케이스 (이론상 어렵지만 페널티 누적 시)
    scores_low = {"ai": 0.0} # Base 0.0
    features_bad = {"text_length": 10} # Penalty -0.10 -> -0.10 -> 0.0
    result_low = calculator.calculate(scores_low, features_bad)
    assert result_low.score == 0.0

def test_recommend_action(calculator):
    """점수 구간별 액션 권고"""
    # Auto Apply (> 0.85)
    res1 = calculator.calculate({"ai": 0.9}) # Base 0.9 -> Auto Apply
    assert res1.action == "auto_apply"
    
    # Suggest (0.60 ~ 0.85)
    res2 = calculator.calculate({"ai": 0.7}) # Base 0.7 -> Suggest
    assert res2.action == "suggest"
    
    # Manual Review (< 0.60)
    res3 = calculator.calculate({"ai": 0.4}) # Base 0.4 -> Manual Review
    assert res3.action == "manual_review"

def test_empty_scores(calculator):
    """점수가 없는 경우"""
    result = calculator.calculate({})
    assert result.score == 0.0
    assert result.action == "manual_review"
    assert "No valid scores provided" in result.reasons

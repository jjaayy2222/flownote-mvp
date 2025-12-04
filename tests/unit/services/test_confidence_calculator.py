# tests/unit/services/test_confidence_calculator.py

import pytest
import logging
from backend.services.confidence_calculator import ConfidenceCalculator

@pytest.fixture
def calculator():
    return ConfidenceCalculator()

def _has_adjustment_with_reason(adjustments, reason):
    """Helper: Check if adjustments contain a specific reason"""
    return any(adj["reason"] == reason for adj in adjustments)

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
    
    # 구조화된 adjustments 확인
    assert _has_adjustment_with_reason(result.details["adjustments"], "Agreement Boost")
    assert result.score > result.details["base_score"]

def test_disagreement_penalty(calculator):
    """분류기 간 불일치 시 페널티 적용"""
    # Negative case: one score below threshold -> no disagreement penalty
    scores = {
        "ai": 0.9,
        "rule": 0.4  # 0.4는 threshold 미만이므로 무시됨 -> Disagreement 발생 안 함
    }
    result_no_disagreement = calculator.calculate(scores)
    base_score_no_disagreement = result_no_disagreement.details["base_score"]

    # "Disagreement Penalty"가 이유에 포함되지 않아야 하고, structured adjustments에도 포함되지 않아야 하며,
    # 최종 점수는 base_score와 같아야 함
    assert all("Disagreement Penalty" not in r for r in result_no_disagreement.reasons)
    assert not _has_adjustment_with_reason(
        result_no_disagreement.details["adjustments"], 
        "Disagreement Penalty"
    )
    assert result_no_disagreement.score == base_score_no_disagreement

    # Positive case: both scores above threshold and sufficiently different -> disagreement penalty
    scores_valid = {
        "ai": 0.95,
        "rule": 0.60
    }
    # 차이 0.35 > 0.3 (0.15 * 2) -> Disagreement Penalty (-0.20)
    result = calculator.calculate(scores_valid)
    
    assert _has_adjustment_with_reason(result.details["adjustments"], "Disagreement Penalty")
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
    assert _has_adjustment_with_reason(result.details["adjustments"], "High Frequency Boost")
    assert _has_adjustment_with_reason(result.details["adjustments"], "Recent Edit Boost")

def test_low_info_penalty(calculator):
    """정보 부족(짧은 텍스트) 페널티"""
    scores = {"ai": 0.7}

    # Case 1: text_length < 50
    features_short = {"text_length": 10}
    result_short = calculator.calculate(scores, features_short)
    assert _has_adjustment_with_reason(result_short.details["adjustments"], "Low Info Penalty")
    
    # Case 2: text_length == 0 (Empty)
    features_empty = {"text_length": 0}
    result_empty = calculator.calculate(scores, features_empty)
    assert _has_adjustment_with_reason(result_empty.details["adjustments"], "Low Info Penalty")

def test_score_clamping(calculator):
    """점수가 0.0 ~ 1.0 범위를 벗어나지 않도록 클램핑"""
    # 1.0 초과 케이스
    scores_high = {"ai": 1.0, "rule": 1.0} # Base 1.0 + Agreement 0.15 = 1.15 -> 1.0
    result_high = calculator.calculate(scores_high)
    assert result_high.score == 1.0
    
    # 0.0 미만 케이스
    scores_low = {"ai": 0.0} # Base 0.0
    features_bad = {"text_length": 10} # Penalty -0.10 -> -0.10 -> 0.0
    result_low = calculator.calculate(scores_low, features_bad)
    assert result_low.score == 0.0

def test_recommend_action(calculator):
    """점수 구간별 액션 권고 (경계값 포함)"""
    # Auto Apply (> 0.85)
    res1 = calculator.calculate({"ai": 0.9})  # Base 0.9 -> Auto Apply
    assert res1.action == "auto_apply"

    # Boundary: Auto Apply (== 0.85)
    # Base 0.85 -> Auto Apply
    res_boundary_auto = calculator.calculate({"ai": 0.85})
    assert res_boundary_auto.action == "auto_apply"

    # Suggest (0.60 ~ 0.85)
    res2 = calculator.calculate({"ai": 0.7})  # Base 0.7 -> Suggest
    assert res2.action == "suggest"

    # Boundary: Suggest (== 0.60)
    # Base 0.60 -> Suggest
    res_boundary_suggest = calculator.calculate({"ai": 0.60})
    assert res_boundary_suggest.action == "suggest"

    # Manual Review (< 0.60)
    res3 = calculator.calculate({"ai": 0.4})  # Base 0.4 -> Manual Review
    assert res3.action == "manual_review"

def test_weights_sum_within_tolerance_no_warning(caplog):
    """가중치 합이 허용 범위 내일 때 경고 없음"""
    class CalculatorWithinTolerance(ConfidenceCalculator):
        _WEIGHTS = {
            "ai": 0.5,
            "human": 0.5,
        }  # Sum = 1.0, within [0.99, 1.01]

    with caplog.at_level(logging.WARNING):
        CalculatorWithinTolerance()

    # 가중치 합 관련 경고가 없어야 함
    weight_warnings = [
        record for record in caplog.records
        if "weight" in record.getMessage().lower() 
        and "sum" in record.getMessage().lower()
    ]
    assert len(weight_warnings) == 0

def test_weights_sum_outside_tolerance_logs_warning(caplog):
    """가중치 합이 허용 범위 밖일 때 경고 발생"""
    class CalculatorOutsideTolerance(ConfidenceCalculator):
        _WEIGHTS = {
            "ai": 0.8,
            "human": 0.3,
        }  # Sum = 1.1, outside [0.99, 1.01]

    with caplog.at_level(logging.WARNING):
        CalculatorOutsideTolerance()

    # 가중치 합 관련 경고가 정확히 1개 있어야 함
    weight_warnings = [
        record for record in caplog.records
        if "weight" in record.getMessage().lower() 
        and "sum" in record.getMessage().lower()
    ]
    assert len(weight_warnings) == 1
    assert "1.1" in weight_warnings[0].getMessage()

def test_empty_scores(calculator):
    """점수가 없는 경우"""
    result = calculator.calculate({})
    assert result.score == 0.0
    assert result.action == "manual_review"
    assert "No valid scores provided" in result.reasons
    
    # Details 검증
    assert result.details["base_score"] == 0.0
    assert result.details["input_scores"] == {}
    assert result.details["adjustments"] == []

def test_complex_scenario_multiple_adjustments(calculator):
    """복합 시나리오: 여러 조정이 동시에 적용되는 경우"""
    scores = {
        "ai": 0.75,
        "rule": 0.70,
        "keyword": 0.72
    }
    # Agreement: 모두 0.6 이상이고 차이 0.05 (< 0.15) -> Boost +0.15
    
    features = {
        "access_frequency": 0.6,   # High freq boost +0.10
        "days_since_edit": 5,      # Recent edit boost +0.05
        "text_length": 30          # Low info penalty -0.10
    }
    
    result = calculator.calculate(scores, features)
    
    # Base score 계산 (가중 평균)
    # ai(0.75*0.4) + rule(0.70*0.25) + keyword(0.72*0.2) = 0.3 + 0.175 + 0.144 = 0.619
    # 총 가중치: 0.85
    # Base: 0.619 / 0.85 ≈ 0.728
    expected_base = round((0.75*0.4 + 0.70*0.25 + 0.72*0.2) / 0.85, 3)
    assert result.details["base_score"] == expected_base
    
    # 조정 확인: Agreement(+0.15) + High Freq(+0.10) + Recent(+0.05) + Low Info(-0.10)
    # = +0.20
    adjustments = result.details["adjustments"]
    assert len(adjustments) == 4
    
    # 각 조정 타입 확인
    adjustment_types = {adj["reason"]: adj["amount"] for adj in adjustments}
    assert adjustment_types["Agreement Boost"] == 0.15
    assert adjustment_types["High Frequency Boost"] == 0.10
    assert adjustment_types["Recent Edit Boost"] == 0.05
    assert adjustment_types["Low Info Penalty"] == -0.10
    
    # 최종 점수: base + 조정 = 0.728 + 0.20 = 0.928
    expected_final = round(expected_base + 0.20, 3)
    assert result.score == expected_final
    assert result.action == "auto_apply"

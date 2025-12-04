# backend/services/confidence_calculator.py

"""
ConfidenceCalculator - 신뢰도 계산 엔진
"""
import logging
from typing import Dict, Any, Optional, List, TypedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class AdjustmentDetail(TypedDict):
    type: str  # 'boost' or 'penalty'
    reason: str
    amount: float


@dataclass
class ConfidenceResult:
    """신뢰도 계산 결과"""
    score: float
    action: str  # 'auto_apply', 'suggest', 'manual_review'
    reasons: List[str]
    details: Dict[str, Any]


class ConfidenceCalculator:
    """
    다양한 분류기의 결과와 파일 특성을 종합하여 최종 신뢰도를 계산합니다.
    
    가중 평균 기반으로 기본 점수를 계산하고, 파일 특성과 분류기 간 동의 여부에 따라
    점수를 조정합니다. 최종 점수를 기반으로 액션(자동 적용, 제안, 수동 검토)을 권고합니다.
    
    Example:
        >>> calculator = ConfidenceCalculator()
        >>> scores = {"ai": 0.9, "rule": 0.85, "keyword": 0.8}
        >>> features = {
        ...     "access_frequency": 0.8,
        ...     "days_since_edit": 3,
        ...     "text_length": 200
        ... }
        >>> result = calculator.calculate(scores, features)
        >>> print(f"Score: {result.score}, Action: {result.action}")
        Score: 1.0, Action: auto_apply
        >>> print(f"Adjustments: {len(result.details['adjustments'])}")
        Adjustments: 3
    
    Attributes:
        _WEIGHTS: 분류기별 가중치 (합계 1.0)
        _ADJUSTMENT_FACTORS: 상황별 점수 조정 팩터
        _THRESHOLDS: 액션 권고 임계값
        _AGREEMENT_THRESHOLD: 유효 점수 최소값
        _AGREEMENT_DIFF_LIMIT: 동의 판단 최대 차이
    """

    # 분류기별 기본 가중치 (총합 1.0)
    _WEIGHTS = {
        "rule": 0.25,
        "keyword": 0.20,
        "ai": 0.40,
        "user": 0.15,
    }

    # 신뢰도 조정 팩터 (Boost / Penalty)
    _ADJUSTMENT_FACTORS = {
        "agreement_boost": 0.15,       # 분류기 간 동의 시
        "high_freq_boost": 0.10,       # 자주 사용되는 파일
        "recent_edit_boost": 0.05,     # 최근 수정된 파일
        "disagreement_penalty": -0.20, # 분류기 간 불일치 시
        "low_info_penalty": -0.10,     # 정보 부족 (짧은 텍스트 등)
    }

    # 액션 권고 임계값
    _THRESHOLDS = {
        "auto_apply": 0.85,
        "suggest": 0.60,
    }

    # 동의 여부 판단 기준
    _AGREEMENT_THRESHOLD = 0.6      # 유효한 점수로 간주할 최소 점수
    _AGREEMENT_DIFF_LIMIT = 0.15    # 동의로 간주할 최대 점수 차이

    def __init__(self):
        """
        ConfidenceCalculator 초기화
        
        가중치 합계가 1.0인지 검증합니다.
        """
        # 가중치 합 검증 (부동소수점 오차 허용)
        total_weight = sum(self._WEIGHTS.values())
        if not (0.99 <= total_weight <= 1.01):
            logger.warning(
                f"Classifier weights sum to {total_weight:.4f}, expected 1.0. "
                f"This may affect score calculations."
            )

    def calculate(
        self,
        scores: Dict[str, float],
        features: Optional[Dict[str, Any]] = None
    ) -> ConfidenceResult:
        """
        최종 신뢰도를 계산하고 액션을 권고합니다.

        Args:
            scores: 각 분류기의 점수 (예: {'rule': 0.8, 'ai': 0.9})
            features: FeatureExtractor에서 추출한 파일 특성

        Returns:
            ConfidenceResult: 계산된 신뢰도 점수와 권고 액션
        """
        features = features or {}
        reasons = []
        adjustments: List[AdjustmentDetail] = []

        # 1. 기본 가중 평균 계산
        base_score = self._calculate_base_score(scores, reasons)
        
        # 2. 신뢰도 조정 (Boost/Penalty)
        adjusted_score = self._apply_adjustments(base_score, scores, features, reasons, adjustments)
        
        # 3. 최종 점수 클램핑 (0.0 ~ 1.0)
        final_score = max(0.0, min(1.0, adjusted_score))
        
        # 4. 액션 권고
        action = self._recommend_action(final_score)

        return ConfidenceResult(
            score=round(final_score, 3),
            action=action,
            reasons=reasons,
            details={
                "base_score": round(base_score, 3),
                "input_scores": scores,
                "adjustments": adjustments
            }
        )

    def _calculate_base_score(self, scores: Dict[str, float], reasons: List[str]) -> float:
        """가중 평균 기반 기본 점수 계산"""
        total_weight = 0.0
        weighted_sum = 0.0

        for source, weight in self._WEIGHTS.items():
            score = scores.get(source)
            if score is not None:
                weighted_sum += score * weight
                total_weight += weight
        
        # 유효한 점수가 하나도 없는 경우
        if total_weight == 0.0:
            reasons.append("No valid scores provided")
            return 0.0

        # 가중치 합이 1이 되도록 정규화하여 평균 계산
        base_score = weighted_sum / total_weight
        reasons.append(f"Base score calculated from {total_weight:.2f} total weight")
        return base_score

    def _apply_adjustments(
        self,
        current_score: float,
        scores: Dict[str, float],
        features: Dict[str, Any],
        reasons: List[str],
        adjustments: List[AdjustmentDetail]
    ) -> float:
        """상황에 따른 점수 조정"""
        adjusted_score = current_score

        def add_adjustment(type_: str, reason: str, amount: float):
            """조정 내역 추가 헬퍼"""
            nonlocal adjusted_score
            adjusted_score += amount
            reasons.append(f"{reason} ({'+' if amount > 0 else ''}{amount})")
            adjustments.append({"type": type_, "reason": reason, "amount": amount})

        # 1. 분류기 간 동의 여부 확인
        if self._check_agreement(scores):
            add_adjustment("boost", "Agreement Boost", self._ADJUSTMENT_FACTORS["agreement_boost"])
        elif self._check_disagreement(scores):
            add_adjustment("penalty", "Disagreement Penalty", self._ADJUSTMENT_FACTORS["disagreement_penalty"])

        # 2. 파일 사용 빈도 (Frequency)
        # FeatureExtractor의 access_frequency가 0.5 이상이면 자주 사용하는 것으로 간주
        access_freq = features.get("access_frequency", 0.0)
        if access_freq >= 0.5:
            add_adjustment("boost", "High Frequency Boost", self._ADJUSTMENT_FACTORS["high_freq_boost"])

        # 3. 최근 수정 여부 (Recency)
        # 7일 이내 수정된 경우
        days_since_edit = features.get("days_since_edit", 999)
        if days_since_edit <= 7:
            add_adjustment("boost", "Recent Edit Boost", self._ADJUSTMENT_FACTORS["recent_edit_boost"])

        # 4. 정보 부족 (텍스트 길이 등)
        # 텍스트 길이 정보가 명시적으로 제공되고, 50자 미만인 경우 (0 포함)
        if "text_length" in features:
            text_length = features["text_length"]
            if text_length < 50:
                add_adjustment("penalty", "Low Info Penalty", self._ADJUSTMENT_FACTORS["low_info_penalty"])

        return adjusted_score

    def _check_agreement(self, scores: Dict[str, float]) -> bool:
        """
        주요 분류기들이 서로 동의하는지 확인
        조건: 유효한 점수(>={self._AGREEMENT_THRESHOLD})가 2개 이상이고, 
              그들의 차이가 작을 때(<={self._AGREEMENT_DIFF_LIMIT})
        """
        valid_scores = [s for s in scores.values() if s >= self._AGREEMENT_THRESHOLD]
        
        if len(valid_scores) < 2:
            return False
            
        return (max(valid_scores) - min(valid_scores)) <= self._AGREEMENT_DIFF_LIMIT

    def _check_disagreement(self, scores: Dict[str, float]) -> bool:
        """
        주요 분류기들이 서로 강하게 불일치하는지 확인
        조건: 유효한 점수(>={self._AGREEMENT_THRESHOLD})가 2개 이상이고, 
              그들의 차이가 클 때(>{self._AGREEMENT_DIFF_LIMIT * 2})
        """
        valid_scores = [s for s in scores.values() if s >= self._AGREEMENT_THRESHOLD]
        
        if len(valid_scores) < 2:
            return False
            
        # 차이가 동의 기준의 2배 이상이면 불일치로 간주
        return (max(valid_scores) - min(valid_scores)) > (self._AGREEMENT_DIFF_LIMIT * 2)

    def _recommend_action(self, score: float) -> str:
        """점수에 따른 액션 권고"""
        if score >= self._THRESHOLDS["auto_apply"]:
            return "auto_apply"
        elif score >= self._THRESHOLDS["suggest"]:
            return "suggest"
        else:
            return "manual_review"

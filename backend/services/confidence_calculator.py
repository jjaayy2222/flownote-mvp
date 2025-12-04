# backend/services/confidence_calculator.py

"""
ConfidenceCalculator - 신뢰도 계산 엔진
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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

        # 1. 기본 가중 평균 계산
        base_score = self._calculate_base_score(scores, reasons)
        
        # 2. 신뢰도 조정 (Boost/Penalty)
        adjusted_score = self._apply_adjustments(base_score, scores, features, reasons)
        
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
                "adjustments": [r for r in reasons if "Boost" in r or "Penalty" in r]
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
        reasons: List[str]
    ) -> float:
        """상황에 따른 점수 조정"""
        adjusted_score = current_score

        # 1. 분류기 간 동의 여부 확인
        if self._check_agreement(scores):
            boost = self._ADJUSTMENT_FACTORS["agreement_boost"]
            adjusted_score += boost
            reasons.append(f"Agreement Boost (+{boost})")
        elif self._check_disagreement(scores):
            penalty = self._ADJUSTMENT_FACTORS["disagreement_penalty"]
            adjusted_score += penalty
            reasons.append(f"Disagreement Penalty ({penalty})")

        # 2. 파일 사용 빈도 (Frequency)
        # FeatureExtractor의 access_frequency가 0.5 이상이면 자주 사용하는 것으로 간주
        access_freq = features.get("access_frequency", 0.0)
        if access_freq >= 0.5:
            boost = self._ADJUSTMENT_FACTORS["high_freq_boost"]
            adjusted_score += boost
            reasons.append(f"High Frequency Boost (+{boost})")

        # 3. 최근 수정 여부 (Recency)
        # 7일 이내 수정된 경우
        days_since_edit = features.get("days_since_edit", 999)
        if days_since_edit <= 7:
            boost = self._ADJUSTMENT_FACTORS["recent_edit_boost"]
            adjusted_score += boost
            reasons.append(f"Recent Edit Boost (+{boost})")

        # 4. 정보 부족 (텍스트 길이 등)
        text_length = features.get("text_length", 0)
        if text_length > 0 and text_length < 50:
            penalty = self._ADJUSTMENT_FACTORS["low_info_penalty"]
            adjusted_score += penalty
            reasons.append(f"Low Info Penalty ({penalty})")

        return adjusted_score

    def _check_agreement(self, scores: Dict[str, float]) -> bool:
        """
        주요 분류기들이 서로 동의하는지 확인
        조건: 유효한 점수(>0.6)가 2개 이상이고, 그들의 차이가 작을 때(<0.15)
        """
        valid_scores = [s for s in scores.values() if s >= self._AGREEMENT_THRESHOLD]
        
        if len(valid_scores) < 2:
            return False
            
        return (max(valid_scores) - min(valid_scores)) <= self._AGREEMENT_DIFF_LIMIT

    def _check_disagreement(self, scores: Dict[str, float]) -> bool:
        """
        주요 분류기들이 서로 강하게 불일치하는지 확인
        조건: 유효한 점수(>0.6)가 2개 이상이고, 그들의 차이가 클 때(>0.3)
        """
        valid_scores = [s for s in scores.values() if s >= self._AGREEMENT_THRESHOLD]
        
        if len(valid_scores) < 2:
            return False
            
        # 차이가 0.3(동의 기준의 2배) 이상이면 불일치로 간주
        return (max(valid_scores) - min(valid_scores)) > (self._AGREEMENT_DIFF_LIMIT * 2)

    def _recommend_action(self, score: float) -> str:
        """점수에 따른 액션 권고"""
        if score >= self._THRESHOLDS["auto_apply"]:
            return "auto_apply"
        elif score >= self._THRESHOLDS["suggest"]:
            return "suggest"
        else:
            return "manual_review"

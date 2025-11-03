# backend/classifier/conflict_resolver.py 생성

"""
Conflict Resolver
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """분류 결과 표준 형식"""
    category: str           # PARA: "Projects" / Keyword: "업무"
    confidence: float       # 0.0 ~ 1.0
    source: str            # "para" or "keyword"
    reasoning: str = ""    # 분류 근거
    tags: Optional[List[str]] = None      # Keyword의 경우 여러 태그 가능


class ConflictResolver:
    """
    PARA vs Keyword 분류 충돌 해결기
    
    핵심 로직:
    1. Confidence 차이가 threshold 이상 → 높은 쪽 선택
    2. 차이가 작으면 → User Review 필요
    """
    
    def __init__(self, confidence_gap_threshold: float = 0.2):
        """
        Args:
            confidence_gap_threshold: 신뢰도 차이 기준
                - 0.2 이상 차이: 명확한 승자
                - 0.2 미만 차이: 모호함 (사용자 검토 필요)
        """
        self.threshold = confidence_gap_threshold
        self.resolution_history = []
        logger.info(f"ConflictResolver initialized (threshold: {self.threshold})")
    
    def resolve(
        self,
        para_result: ClassificationResult,
        keyword_result: ClassificationResult
    ) -> Dict[str, Any]:
        """
        두 분류 결과 통합
        
        Returns:
            {
                "final_category": str,
                "para_category": str,
                "keyword_tags": list,
                "confidence": float,
                "confidence_gap": float,  # 추가됨
                "conflict_detected": bool,
                "resolution_method": str,
                "requires_review": bool,
                "para_reasoning": str,
                "reason": str
            }
        """
        
        # 1. Confidence 차이 계산
        gap = abs(para_result.confidence - keyword_result.confidence)
        
        # 2. 승자 결정
        if gap >= self.threshold:
            # 명확한 승자
            winner = self._select_winner(para_result, keyword_result)
            result = {
                "final_category": winner.category,
                "para_category": para_result.category,
                "keyword_tags": keyword_result.tags or [keyword_result.category],
                "confidence": winner.confidence,
                "confidence_gap": round(gap, 3),  # 추가됨
                "conflict_detected": False,
                "resolution_method": "auto_by_confidence",
                "requires_review": False,
                "winner_source": winner.source,
                "para_reasoning": para_result.reasoning,
                "reason": f"명확한 승자 선택됨 (Gap: {gap:.2f})"
            }
        else:
            # 모호한 상황 → User Review
            result = {
                "final_category": para_result.category,  # 임시로 PARA 우선
                "para_category": para_result.category,
                "keyword_tags": keyword_result.tags or [keyword_result.category],
                "confidence": max(para_result.confidence, keyword_result.confidence),
                "confidence_gap": round(gap, 3),
                "conflict_detected": True,
                "resolution_method": "pending_user_review",
                "requires_review": True,
                "para_reasoning": para_result.reasoning,
                "reason": f"모호한 상황 감지됨 (Gap: {gap:.2f} < Threshold: {self.threshold})"
            }
        
        # 3. 히스토리 저장
        self._save_to_history(para_result, keyword_result, result)
        
        logger.info(
            f"Resolved: {result['final_category']} "
            f"(conflict: {result['conflict_detected']}, "
            f"review: {result['requires_review']})"
        )
        
        return result
    
    def _select_winner(
        self,
        result1: ClassificationResult,
        result2: ClassificationResult
    ) -> ClassificationResult:
        """신뢰도 높은 쪽 선택"""
        return result1 if result1.confidence >= result2.confidence else result2
    
    def _save_to_history(
        self,
        para: ClassificationResult,
        keyword: ClassificationResult,
        resolution: Dict
    ):
        """해결 이력 저장 (디버깅용)"""
        self.resolution_history.append({
            "para": para,
            "keyword": keyword,
            "resolution": resolution
        })
        
        # 최대 1000개만 유지
        if len(self.resolution_history) > 1000:
            self.resolution_history = self.resolution_history[-1000:]
    
    def get_statistics(self) -> Dict:
        """통계 정보"""
        if not self.resolution_history:
            return {"total": 0}
        
        total = len(self.resolution_history)
        conflicts = sum(
            1 for h in self.resolution_history 
            if h["resolution"]["conflict_detected"]
        )
        auto_resolved = total - conflicts
        
        return {
            "total_resolutions": total,
            "conflicts_detected": conflicts,
            "conflict_rate": round(conflicts / total, 3) if total > 0 else 0,
            "auto_resolved": auto_resolved,
            "auto_resolve_rate": round(auto_resolved / total, 3) if total > 0 else 0
        }

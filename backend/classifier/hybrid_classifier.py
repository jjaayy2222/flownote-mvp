# backend/classifier/hybrid_classifier.py

"""
HybridClassifier - 규칙 기반과 AI 기반을 결합한 하이브리드 분류기
"""

import logging
from typing import Dict, Any, Optional

from backend.classifier.base_classifier import BaseClassifier
from backend.services.rule_engine import RuleEngine
from backend.classifier.ai_classifier import AIClassifier

logger = logging.getLogger(__name__)


class HybridClassifier(BaseClassifier):
    """
    RuleEngine(1차) -> AIClassifier(2차) 순서로 분류를 수행하는 하이브리드 분류기.
    """

    def __init__(
        self,
        rule_engine: Optional[RuleEngine] = None,
        ai_classifier: Optional[AIClassifier] = None,
    ):
        """
        초기화

        Args:
            rule_engine: 주입된 RuleEngine (없으면 기본 생성)
            ai_classifier: 주입된 AIClassifier (없으면 기본 생성)
        """
        super().__init__()
        self.rule_engine = rule_engine or RuleEngine()
        self.ai_classifier = ai_classifier or AIClassifier()
        # 룰 매칭으로 인정할 최소 신뢰도 (이 값 이상이면 AI 호출 안 함)
        self.rule_threshold = 0.8

    async def classify(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        하이브리드 분류 수행

        1. RuleEngine 평가
        2. 신뢰도가 threshold 이상이면 즉시 반환
        3. 아니면 AIClassifier 호출
        """
        if not text or not text.strip():
            return self._default_result("Input text is empty")

        # 1. Rule-based Classification (Synchronous)
        try:
            rule_result = self.rule_engine.evaluate(text, metadata=context)

            if rule_result and rule_result.confidence >= self.rule_threshold:
                logger.info(
                    f"Rule matched: {rule_result.category} (conf: {rule_result.confidence})"
                )
                return {
                    "category": rule_result.category,
                    "confidence": rule_result.confidence,
                    "reasoning": f"Rule matched: {rule_result.matched_rule}",
                    "keywords": [],
                    "method": "rule",
                }
        except Exception as e:
            logger.warning(f"RuleEngine failed, proceeding to AI: {e}")

        # 2. AI-based Classification (Asynchronous)
        try:
            logger.info("Rule mismatch or low confidence, falling back to AIClassifier")
            ai_result = await self.ai_classifier.classify(text, context)

            # AI 결과에 method 필드가 없으면 강제 주입 (AIClassifier가 보장하지만 이중 안전장치)
            if "method" not in ai_result:
                ai_result["method"] = "ai"
            return ai_result

        except Exception as e:
            logger.error(f"Hybrid classification failed: {e}", exc_info=True)
            self.last_error = str(e)
            return self._default_result(f"Error: {str(e)}")

    def _default_result(self, reason: str) -> Dict[str, Any]:
        return {
            "category": "Unclassified",
            "confidence": 0.0,
            "reasoning": reason,
            "keywords": [],
            "method": "hybrid_error",
        }

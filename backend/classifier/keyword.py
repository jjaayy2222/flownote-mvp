# backend/classifier/keyword.py

"""
KeywordClassifier - Async 지원
"""
import asyncio
import logging
from typing import Dict, Any
from classifier.base_classifier import BaseClassifier

logger = logging.getLogger(__name__)


class KeywordClassifier(BaseClassifier):
    """키워드 기반 분류기"""

    def __init__(self):
        super().__init__()
        self.keyword_rules = {
            "Projects": ["urgent", "deadline", "task", "project", "todo"],
            "Areas": ["ongoing", "maintain", "update", "improve"],
            "Resources": ["reference", "guide", "tutorial", "template"],
            "Archives": ["done", "completed", "finished", "archived"]
        }

    async def classify(
        self, text: str, context: dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """키워드 기반 분류"""
        try:
            # 오래 걸리는 작업은 thread pool에서 실행
            result = await asyncio.to_thread(
                self._classify_sync, text, context
            )
            
            # 검증
            is_valid, error_msg = self.validate_result(result)
            if not is_valid:
                logger.warning(f"Validation failed: {error_msg}")
                return self._default_result()
            
            return result

        except Exception as e:
            logger.error(f"Keyword classification failed: {str(e)}")
            self.last_error = str(e)
            return self._default_result()

    def _classify_sync(
        self, text: str, context: dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """동기식 분류 로직"""
        scores = {cat: 0 for cat in self.keyword_rules.keys()}
        matched_keywords = {cat: [] for cat in self.keyword_rules.keys()}
        
        text_lower = text.lower()
        
        # 키워드 매칭
        for category, keywords in self.keyword_rules.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    scores[category] += 1
                    matched_keywords[category].append(keyword)
        
        # 최고 점수 카테고리 선택
        max_score = max(scores.values())
        if max_score == 0:
            best_category = "Inbox"
            confidence = 0.0
        else:
            best_category = max(scores, key=scores.get)
            total_keywords = sum(len(kw) for kw in self.keyword_rules.values())
            confidence = min(1.0, max_score / total_keywords)
        
        return {
            "category": best_category,
            "confidence": confidence,
            "reasoning": f"Matched {scores[best_category]} keywords: {', '.join(matched_keywords[best_category])}",
            "method": "keyword",
            "metadata": {
                "matched_keywords": matched_keywords[best_category],
                "scores": scores
            }
        }

    def _default_result(self) -> Dict[str, Any]:
        """기본 결과"""
        return {
            "category": "Inbox",
            "confidence": 0.0,
            "reasoning": "Keyword classification error",
            "method": "keyword",
            "metadata": {}
        }

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
        # 1. 기본 규칙 복사 (리스트까지 새로 생성하여 참조 끊기 - Deep Copy 효과)
        current_rules = {k: list(v) for k, v in self.keyword_rules.items()}
        
        # 2. Context 반영 (사용자 Areas를 키워드로 추가)
        user_areas = []
        if context and "areas" in context:
            user_areas = [a.lower() for a in context["areas"]]
            if user_areas:
                if "Areas" not in current_rules:
                    current_rules["Areas"] = []
                current_rules["Areas"].extend(user_areas)

        scores = {cat: 0 for cat in current_rules}
        matched_keywords = {cat: [] for cat in current_rules}
        
        text_lower = text.lower()
        user_areas_matched = False
        
        # 3. 키워드 매칭
        for category, keywords in current_rules.items():
            for keyword in keywords:
                kw_lower = keyword.lower()
                if kw_lower in text_lower:
                    scores[category] += 1
                    matched_keywords[category].append(keyword)
                    
                    # 사용자 Context(Areas)와 매칭되었는지 확인
                    if kw_lower in user_areas:
                        user_areas_matched = True
                        scores[category] += 2  # 가중치 부여
        
        # 4. 최고 점수 카테고리 선택
        max_score = max(scores.values())
        if max_score == 0:
            best_category = "Inbox"
            confidence = 0.0
        else:
            best_category = max(scores, key=scores.get)
            # 신뢰도 계산 개선: 키워드 1개당 0.3점, 최대 0.95
            confidence = min(0.95, max_score * 0.3)
        
        return {
            "category": best_category,
            "confidence": confidence,
            "reasoning": f"Matched {scores[best_category]} keywords: {', '.join(matched_keywords[best_category])}",
            "method": "keyword",
            "metadata": {
                "matched_keywords": matched_keywords[best_category],
                "scores": scores,
                "user_context_matched": user_areas_matched
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

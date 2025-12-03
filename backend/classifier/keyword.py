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
        # 1. 기본 규칙 복사
        current_rules = self.keyword_rules.copy()
        
        # 2. Context 반영 (사용자 Areas를 키워드로 추가)
        user_areas_matched = False
        if context and "areas" in context:
            for area in context["areas"]:
                # Areas 카테고리에 사용자 정의 영역 키워드 추가
                if "Areas" not in current_rules:
                    current_rules["Areas"] = []
                current_rules["Areas"].append(area.lower())

        scores = {cat: 0 for cat in current_rules.keys()}
        matched_keywords = {cat: [] for cat in current_rules.keys()}
        
        text_lower = text.lower()
        
        # 3. 키워드 매칭
        for category, keywords in current_rules.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    scores[category] += 1
                    matched_keywords[category].append(keyword)
                    
                    # 사용자 Context(Areas)와 매칭되었는지 확인
                    if context and "areas" in context and keyword.lower() in [a.lower() for a in context["areas"]]:
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

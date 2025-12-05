# backend/classifier/ai_classifier.py

"""
AIClassifier - LLM 기반 분류기
"""
import logging
import json
import asyncio
from typing import Dict, Any, Optional

from backend.classifier.base_classifier import BaseClassifier
from backend.services.gpt_helper import GPT4oHelper

logger = logging.getLogger(__name__)

# 시스템 프롬프트 정의
_SYSTEM_PROMPT = """
You are a highly intelligent personal knowledge management assistant trained in the PARA method (Projects, Areas, Resources, Archives).
Your task is to classify the given text into one of the PARA categories.

Definitions:
- Projects: A series of tasks linked to a goal, with a deadline. (e.g., "Complete app launch", "Write blog post")
- Areas: A sphere of activity with a standard to be maintained over time. (e.g., "Health", "Finances", "Professional Development")
- Resources: A topic or theme of ongoing interest. (e.g., "Python coding", "Design patterns", "Stock market data")
- Archives: Inactive items from the other three categories. (e.g., "Completed projects", "Old receipts")

Instructions:
1. Analyze the content deeply.
2. Determine the most suitable PARA category.
3. Provide a confidence score between 0.0 and 1.0.
4. Briefly explain your reasoning.
5. Return the result in STRICT JSON format.

Output JSON Schema:
{
    "category": "Projects" | "Areas" | "Resources" | "Archives",
    "confidence": float,
    "reason": "string",
    "keywords": ["string", "string"]
}
"""


class AIClassifier(BaseClassifier):
    """
    GPT를 활용하여 텍스트를 PARA 카테고리로 분류하는 분류기.
    """

    def __init__(self, gpt_helper: Optional[GPT4oHelper] = None):
        """
        초기화

        Args:
            gpt_helper: GPT4oHelper 인스턴스 (테스트 시 mock 주입 가능)
        """
        super().__init__()
        self.gpt_helper = gpt_helper or GPT4oHelper()

    async def classify(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        텍스트를 분석하여 PARA 카테고리를 반환합니다.

        Args:
            text: 분석할 텍스트 내용
            context: 추가 컨텍스트 (사용자 정보 등)

        Returns:
            Dict[str, Any]: 분류 결과 (category, confidence, reasoning 등)
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to AIClassifier")
            return self._default_result("Input text is empty")

        try:
            # 사용자 메시지 구성
            user_message = f"Content to classify:\n---\n{text}\n---"

            if context:
                # 컨텍스트가 있으면 프롬프트에 추가 (예: 최근 작업 내역 등)
                user_message += (
                    f"\n\nContext:\n{json.dumps(context, ensure_ascii=False)}"
                )

            # GPT 호출 (동기 메서드를 비동기로 래핑)
            # _call 메서드는 내부 메서드지만, 유연한 프롬프트 제어를 위해 사용
            response_text = await asyncio.to_thread(
                self.gpt_helper._call,
                prompt=user_message,
                system_prompt=_SYSTEM_PROMPT,
                max_tokens=200,
            )

            if not response_text:
                raise ValueError("Received empty response from GPT")

            # JSON 파싱
            result = self._parse_response(response_text)

            # 결과 검증
            is_valid, error_msg = self.validate_result(result)
            if not is_valid:
                logger.warning(f"Invalid AI classification result: {error_msg}")
                # 검증 실패 시 로그 남기고 Unclassified 처리 (단, method 필드는 포함해야 함)
                return self._default_result(f"Validation failed: {error_msg}")

            return result

        except Exception as e:
            logger.error(f"AI classification failed: {str(e)}", exc_info=True)
            self.last_error = str(e)
            return self._default_result(f"Error: {str(e)}")

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """GPT 응답 텍스트를 파싱하여 딕셔너리로 변환"""
        try:
            # 이미 GPT4oHelper._call에서 마크다운 정리는 수행되지만,
            # 혹시 모를 상황에 대비해 파싱 시도
            text = response_text.strip()

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 2차 시도: 혹시 마크다운이 남아있다면 제거
                if "```" in text:
                    text = text.split("```json")[-1].split("```")[0].strip()
                data = json.loads(text)

            return {
                "category": data.get("category", "Resources"),  # 기본값
                "confidence": float(data.get("confidence", 0.5)),
                "reasoning": data.get("reason", "No reason provided"),
                "keywords": data.get("keywords", []),
                "method": "ai",  # BaseClassifier 필수 필드
            }
        except Exception:
            logger.warning(f"Failed to parse JSON response: {response_text}")
            return self._default_result("JSON parsing failed")

    def _default_result(self, reason: str = "Unknown error") -> Dict[str, Any]:
        """실패 시 반환할 기본 결과"""
        return {
            "category": "Unclassified",
            "confidence": 0.0,
            "reasoning": reason,
            "keywords": [],
            "method": "ai",  # BaseClassifier 필수 필드
        }

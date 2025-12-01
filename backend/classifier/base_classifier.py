# backend/classifier/base_classifier.py

"""
BaseClassifier - 모든 분류기의 추상 클래스
Async 지원 + 타입 힌팅
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class BaseClassifier(ABC):
    """모든 분류기의 기본 인터페이스"""

    def __init__(self):
        self.name = self.__class__.__name__
        self.last_error: str | None = None

    @abstractmethod
    async def classify(
        self, text: str, context: dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """
        분류 수행
        
        Args:
            text: 분류할 텍스트
            context: 추가 컨텍스트 정보
            
        Returns:
            {
                "category": str,       # Projects, Areas, Resources, Archives
                "confidence": float,   # 0.0 ~ 1.0
                "reasoning": str,      # 분류 이유
                "method": str,         # "rule", "keyword", "ai"
                "metadata": dict       # 추가 정보
            }
        """
        pass

    def validate_result(
        self, result: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """분류 결과 검증"""
        required_fields = ["category", "confidence", "reasoning", "method"]
        for field in required_fields:
            if field not in result:
                error_msg = f"Missing required field: {field}"
                logger.error(error_msg)
                self.last_error = error_msg
                return False, error_msg

        if not isinstance(result["confidence"], (int, float)):
            error_msg = "confidence must be a number"
            self.last_error = error_msg
            return False, error_msg

        if not 0 <= result["confidence"] <= 1:
            error_msg = "confidence must be between 0 and 1"
            self.last_error = error_msg
            return False, error_msg

        self.last_error = None
        return True, "valid"

    def get_error(self) -> str | None:
        """마지막 에러 반환"""
        return self.last_error

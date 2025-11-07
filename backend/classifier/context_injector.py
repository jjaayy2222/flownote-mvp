# backend/classifier/context_injector.py 

"""
사용자 맥락을 프롬프트에 주입하는 모듈
"""

import json
import logging
import os
import sys
import re
from typing import Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv


# ============================================================
# 1. 동적 경로 계산 (상대경로 + .env 자동로드)
# ============================================================

CURRENT_FILE = Path(__file__)
CLASSIFIER_DIR = CURRENT_FILE.parent
BACKEND_DIR = CLASSIFIER_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# .env 파일 자동 로드
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(str(ENV_FILE))

# ============================================================
# 2. sys.path에 경로 명시적 추가
# ============================================================

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# 3. 임포트
# ============================================================

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# ============================================================
# 4. Config Import (3-tier Fallback)
# ============================================================

try:
    from backend.config import ModelConfig
    logger_msg = "✅ ModelConfig loaded from backend.config"
except ImportError:
    try:
        from config import ModelConfig
        logger_msg = "✅ ModelConfig loaded from config"
    except ImportError:
        logger_msg = "⚠️  Using os.getenv fallback"
        class ModelConfig:
            GPT4O_MINI_API_KEY = os.getenv("GPT4O_API_KEY")
            GPT4O_MINI_BASE_URL = os.getenv("GPT4O_BASE_URL")
            GPT4O_MINI_MODEL = os.getenv("GPT4O_MODEL", "gpt-4o")

logger = logging.getLogger(__name__)
logger.info(logger_msg)

# ============================================================
# 5. ContextInjectorClassifier 클래스
# ============================================================

class ContextInjector:
    """사용자 맥락 주입기"""
    
    def __init__(self, context_file: str = "data/context/user_context_mapping.json"):
        # 파일 경로: /data/context/user_context_mapping.json
        """
        Args:
            context_file: 사용자 맥락 JSON 파일 경로
        """
        self.context_file = Path(context_file)
        self.contexts = self._load_contexts()
    
    def _load_contexts(self) -> Dict[str, Any]:
        """JSON 파일에서 맥락 로드"""
        try:
            if self.context_file.exists():
                with open(self.context_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.warning(f"맥락 파일 로드 실패: {str(e)}")
            return {}

    def _format_context(self, context_data: Dict[str, Any]) -> str:
        """맥락 데이터를 프롬프트 형식으로 포맷팅"""
        try:
            formatted_parts = []
            
            if context_data.get("user_interests"):
                formatted_parts.append(
                    f"사용자 관심사: {', '.join(context_data['user_interests'])}"
                )
            
            if context_data.get("expertise_level"):
                formatted_parts.append(
                    f"전문 수준: {context_data['expertise_level']}"
                )
            
            if context_data.get("preferred_style"):
                formatted_parts.append(
                    f"선호 스타일: {context_data['preferred_style']}"
                )
            
            if context_data.get("goals"):
                formatted_parts.append(
                    f"목표: {', '.join(context_data['goals'])}"
                )
            
            return "\n".join(formatted_parts) if formatted_parts else ""
        
        except Exception as e:
            logger.error(f"맥락 포맷팅 실패: {str(e)}")
            return ""

    def inject_context_to_prompt(self, user_id: str, base_prompt: str) -> str:
        """
        기존: 파일 기반 맥락 주입 (유지)
        
        사용자 맥락을 기존 프롬프트에 주입
        
        Args:
            user_id: 사용자 ID
            base_prompt: 기본 프롬프트
            
        Returns:
            맥락이 주입된 프롬프트
        """
        try:
            context = self.contexts.get(user_id, {})
            
            if not context:
                logger.debug(f"사용자 {user_id}의 맥락 없음")
                return base_prompt
            
            formatted_context = self._format_context(context)
            
            if formatted_context:
                return f"{base_prompt}\n\n[사용자 맥락]\n{formatted_context}"
            
            return base_prompt
        
        except Exception as e:
            logger.error(f"프롬프트 주입 실패: {str(e)}")
            return base_prompt

    def inject_context_from_user_id(self, user_id: str, ai_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        🆕 온보딩 기반: user_id로 data_manager에서 조회하여 AI 결과에 주입
        
        온보딩에서 수집한 사용자 정보를 활용하여
        AI 분석 결과에 사용자 맥락 정보 추가
        
        Args:
            user_id: 사용자 ID
            ai_result: AI 분석 결과 dict
            
        Returns:
            맥락이 추가된 ai_result dict
        """
        try:
            # data_manager 동적 로드 (순환 참조 방지)
            from backend.data_manager import DataManager
            
            dm = DataManager()
            
            # 온보딩 결과 조회
            user_profile = dm.get_user_profile(user_id)
            user_context = dm.get_user_context(user_id)
            
            if not user_profile or not user_context:
                logger.debug(f"사용자 {user_id}의 프로필/맥락 없음")
                ai_result["context_injected"] = False
                return ai_result
            
            # 기존 포맷팅 함수 활용
            formatted_context = self._format_context(user_context)
            
            # AI 결과에 맥락 정보 추가
            ai_result["user_context"] = formatted_context
            ai_result["user_profile"] = {
                "name": user_profile.get("name", ""),
                "expertise_level": user_context.get("expertise_level", ""),
            }
            ai_result["context_injected"] = True
            
            logger.info(f"사용자 {user_id}의 맥락 주입 완료")
            return ai_result
        
        except Exception as e:
            logger.error(f"사용자 맥락 주입 실패: {str(e)}")
            ai_result["context_injected"] = False
            return ai_result

    def inject_from_file_metadata(self, file_metadata: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        파일 메타데이터 기반 맥락 주입 (향후 확장용)
        """
        try:
            context = self.contexts.get(user_id, {})
            
            result = {
                "file_context": file_metadata,
                "user_context": self._format_context(context),
                "enriched": bool(context)
            }
            
            return result
        
        except Exception as e:
            logger.error(f"파일 메타데이터 맥락 주입 실패: {str(e)}")
            return {
                "file_context": file_metadata,
                "user_context": "",
                "enriched": False
            }

# 싱글톤 패턴: 전역 인스턴스
_context_injector_instance: Optional[ContextInjector] = None

def get_context_injector() -> ContextInjector:
    """ContextInjector 싱글톤 반환"""
    global _context_injector_instance
    
    if _context_injector_instance is None:
        _context_injector_instance = ContextInjector()
    
    return _context_injector_instance






"""test_result ✓

    `data/context/user_context_mapping.json` → 호출해보기 

    ============================================================
    사용자 맥락:
    null

    ============================================================
    주입된 프롬프트:

    사용자 정보:
    - 직업: 알 수 없음
    - 책임 영역: 없음
    - 관심사: 없음

    각 관심사별 P/A/R 의미:
    {}

    ============================================================
    관심사별 키워드:
    {}

"""




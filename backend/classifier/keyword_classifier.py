# backend/classifier/keyword_classifier.py

"""
키워드 기반 분류기 - LLM 기반 (프록시 API 지원)
LangChain 통합 + 완벽한 JSON 출력 보장

구조:
- 동적 경로 계산 (.env 자동 로드)
- sys.path에 명시적 추가
- 3-tier fallback import (절대 → 상대 → 환경변수)
- 강화된 프롬프트 (JSON 지시 명확)
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
            GPT4O_MINI_API_KEY = os.getenv("GPT4O_MINI_API_KEY")
            GPT4O_MINI_BASE_URL = os.getenv("GPT4O_MINI_BASE_URL")
            GPT4O_MINI_MODEL = os.getenv("GPT4O_MINI_MODEL", "gpt-4o-mini")

logger = logging.getLogger(__name__)
logger.info(logger_msg)


# ============================================================
# 5. KeywordClassifier 클래스
# ============================================================

class KeywordClassifier:
    """키워드 기반 분류기 (LLM 기반 - GPT-4o-mini)"""

    def __init__(self):
        """KeywordClassifier 초기화"""
        self.llm = None
        self.chain = None
        self._initialize_llm()
        self._load_prompt()

    def _initialize_llm(self):
        """LLM 초기화"""
        try:
            api_key = ModelConfig.GPT4O_MINI_API_KEY
            if not api_key:
                raise ValueError("❌ GPT4O_MINI_API_KEY not set")
            
            self.llm = ChatOpenAI(
                api_key=api_key,
                base_url=ModelConfig.GPT4O_MINI_BASE_URL,
                model=ModelConfig.GPT4O_MINI_MODEL,
                temperature=0.0,
                max_tokens=600,
            )
            
            logger.info("✅ KeywordClassifier LLM 초기화 성공")
            
        except Exception as e:
            logger.error(f"❌ LLM 초기화 실패: {e}")
            self.llm = None

    def _load_prompt(self):
        """프롬프트 파일 로드 및 Chain 생성"""
        try:
            prompt_path = CLASSIFIER_DIR / "prompts" / "keyword_classification_prompt.txt"
            
            if not prompt_path.exists():
                raise FileNotFoundError(f"프롬프트 파일 없음: {prompt_path}")
            
            with open(prompt_path, "r", encoding="utf-8") as f:
                template_content = f.read()
            
            # ✅ 중요: {text} 변수만 남기고 나머지 { } 이스케이프
            escaped_content = self._escape_prompt_braces(template_content)
            
            # ChatPromptTemplate 생성
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a keyword extraction and classification expert. Always respond with valid JSON only."),
                ("user", escaped_content)
            ])
            
            # Chain 생성: Prompt → LLM → StrOutputParser
            if self.llm:
                self.chain = prompt | self.llm | StrOutputParser()
                logger.info("✅ 프롬프트 로드 및 Chain 생성 성공")
            else:
                logger.warning("⚠️  LLM 미초기화로 Chain 생성 불가")
            
        except Exception as e:
            logger.error(f"❌ 프롬프트 로드 실패: {e}")
            self.chain = None
    
    def _escape_prompt_braces(self, content: str) -> str:
        """
        프롬프트의 중괄호 이스케이프 (핵심!)
        {text} 변수만 남기고 나머지 모든 { } 를 {{ }} 로 변환
        """
        lines = []
        for line in content.split('\n'):
            # {text}가 있는 라인은 그대로 유지
            if '{text}' in line:
                lines.append(line)
            else:
                # 나머지 라인의 { } 를 {{ }} 로 변환
                # 단, 이미 이스케이프된 {{ }} 는 건드리지 않음
                escaped_line = line.replace('{', '{{').replace('}', '}}')
                # {{{{ → {{ 로 중복 이스케이프 방지
                escaped_line = escaped_line.replace('{{{{', '{{').replace('}}}}', '}}')
                lines.append(escaped_line)
        
        return '\n'.join(lines)

    def classify(self, text: str) -> Dict[str, Any]:
        """텍스트 분류 (LLM 기반)"""
        # 빈 텍스트 확인
        if not text or not text.strip():
            logger.warning("⚠️  빈 텍스트 입력")
            return self._create_empty_response()

        # Chain 미초기화 확인
        if self.chain is None:
            logger.warning("⚠️  Chain 미초기화, Fallback 사용")
            return self._fallback_classify(text)

        try:
            # 🔥 LLM 호출 (Chain 사용)
            logger.info(f"🚀 LLM 호출 시작: {text[:50]}...")
            response_text = self.chain.invoke({"text": text})
            
            # 디버깅: 원본 응답 출력
            print(f"\n{'='*80}")
            print(f"🔍 원본 LLM 응답:")
            print(f"{'='*80}")
            print(response_text)
            print(f"{'='*80}\n")
            
            # JSON 추출
            json_text = self._extract_json_from_response(response_text)
            
            # 디버깅: 추출된 JSON
            print(f"📄 추출된 JSON:")
            print(json_text)
            print()
            
            # JSON 파싱
            result = json.loads(json_text)
            
            # 성공 로그
            logger.info(f"✅ LLM 분류 성공: {result.get('tags', [])}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 파싱 실패: {e}")
            logger.debug(f"파싱 시도 텍스트: {json_text[:300] if 'json_text' in locals() else 'N/A'}")
            return self._fallback_classify(text)
            
        except Exception as e:
            logger.error(f"❌ 분류 오류: {type(e).__name__}: {e}")
            logger.error(f"상세 에러: {str(e)}")
            return self._fallback_classify(text)

    def _extract_json_from_response(self, response_text: str) -> str:
        """LLM 응답에서 JSON 추출"""
        response_text = response_text.strip()
        
        # Step 1: ```json ... ``` 형식
        if "```json" in response_text:
            match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        # Step 2: ``` ... ``` 형식
        if "```" in response_text:
            match = re.search(r'```\s*(.*?)\s*```', response_text, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        # Step 3: { ... } JSON 객체 찾기
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            return match.group(0)
        
        # Step 4: 실패 - 전체 반환
        logger.warning("⚠️  JSON 포맷 찾기 실패")
        return response_text

    def _fallback_classify(self, text: str) -> Dict[str, Any]:
        """Fallback 분류 (키워드 매칭)"""
        keywords_map = {
            "업무": ["회의", "업무", "작업", "프로젝트", "계획", "보고서", "미팅", "팀", "협업"],
            "학습": ["공부", "학습", "강의", "스터디", "교육", "자격증", "연구", "독서"],
            "개인": ["일기", "메모", "생각", "일상", "감정", "회고", "기록", "노트"],
            "건강": ["운동", "건강", "헬스", "요가", "식단", "수면", "명상", "병원"],
            "재무": ["예산", "지출", "투자", "저축", "재테크", "세금", "월급", "카드"],
        }
        
        matched_dict = {}
        for category, keywords in keywords_map.items():
            matched = [kw for kw in keywords if kw in text]
            if matched:
                matched_dict[category] = matched
        
        if not matched_dict:
            return self._create_empty_response()
        
        total_matched = sum(len(kws) for kws in matched_dict.values())
        base_confidence = min(total_matched / 5, 0.7)
        if total_matched >= 2:
            base_confidence += 0.15
        confidence = min(base_confidence + 0.10, 1.0)
        
        logger.info(f"🔄 Fallback 분류: {list(matched_dict.keys())}")
        
        return {
            "tags": list(matched_dict.keys())[:3],
            "confidence": round(confidence, 2),
            "matched_keywords": matched_dict,
            "reasoning": f"Fallback: {total_matched}개 키워드 감지",
            "para_hints": {cat: ["Areas"] for cat in matched_dict.keys()},
            "is_fallback": True
        }

    def _create_empty_response(self) -> Dict[str, Any]:
        """빈 응답"""
        return {
            "tags": ["기타"],
            "confidence": 0.0,
            "matched_keywords": {},
            "reasoning": "명확한 키워드가 감지되지 않음",
            "para_hints": {"기타": ["Resources"]},
        }

    def get_statistics(self) -> Dict[str, Any]:
        """분류기 통계"""
        return {
            "llm_initialized": self.llm is not None,
            "chain_initialized": self.chain is not None,
            "model": ModelConfig.GPT4O_MINI_MODEL if self.llm else "None",
            "api_configured": bool(ModelConfig.GPT4O_MINI_API_KEY),
        }


# ============================================================
# 테스트 메인 함수
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    print("\n" + "="*70)
    print("KeywordClassifier 테스트")
    print("="*70)
    
    classifier = KeywordClassifier()
    
    stats = classifier.get_statistics()
    print("\n📊 분류기 상태:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    test_texts = [
        "오늘 회의가 있고, 저녁에 스터디 모임이 있습니다.",
        "일기를 쓰면서 오늘 하루를 돌아봅니다.",
        "오늘 헬스장에 가서 운동했습니다.",
    ]
    
    print("\n" + "="*70)
    print("분류 테스트")
    print("="*70)
    
    for i, text in enumerate(test_texts, 1):
        print(f"\n📝 테스트 {i}: {text}")
        result = classifier.classify(text)
        print(f"✅ 태그: {result['tags']}")
        print(f"📊 신뢰도: {result['confidence']}")
        print(f"🔑 키워드: {result['matched_keywords']}")



"""test_result_1 → ❌

    `Syntax Error → 로직 완전 꼬임 → json 파싱 시도 전 에러 → 로직 정리 필요`

    ======================================================================
    KeywordClassifier 테스트
    ======================================================================
    2025-11-02 12:09:07,834 - __main__ - INFO - ✅ KeywordClassifier LLM 초기화 성공 (gpt-4o-mini)
    2025-11-02 12:09:07,834 - __main__ - INFO - ✅ 프롬프트 파일 로드 성공

    📊 분류기 상태:
        llm_initialized: True
        prompt_loaded: True
        model: openai/gpt-4o-mini
        api_configured: True
        project_root: ***/flownote-mvp/
        classifier_dir: ***/flownote-mvp/backend/classifier/

    ======================================================================
    분류 테스트 실행
    ======================================================================

    📝 테스트 1:
    입력: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다. 프로젝트 진행 상황을 공유하고 새로운 ...
    2025-11-02 12:09:07,834 - __main__ - ERROR - ❌ 오류: '\n  "tags"'
    ✅ 태그: ['기타']
    📊 신뢰도: 0.0
    🔑 키워드: {}

    📝 테스트 2:
    입력: 일기를 쓰면서 오늘 하루를 돌아봅니다. 감정을 정리하고 내일 할 일을 생각해봤습니다....
    2025-11-02 12:09:07,834 - __main__ - ERROR - ❌ 오류: '\n  "tags"'
    ✅ 태그: ['기타']
    📊 신뢰도: 0.0
    🔑 키워드: {}

    📝 테스트 3:
    입력: 오늘 헬스장에 가서 운동했습니다. PT 세션도 받고 식단 상담도 받았어요....
    2025-11-02 12:09:07,834 - __main__ - ERROR - ❌ 오류: '\n  "tags"'
    ✅ 태그: ['기타']
    📊 신뢰도: 0.0
    🔑 키워드: {}

"""


"""test_result_2 → 🔼

    `원본 LLM이 응답 출력하고 있지 않음 → 디버깅 강화 코드 추가 필요`

    ======================================================================
    KeywordClassifier 테스트
    ======================================================================
    2025-11-02 12:40:12,177 - __main__ - INFO - ✅ KeywordClassifier LLM 초기화 성공 (gpt-4o-mini)
    2025-11-02 12:40:12,178 - __main__ - INFO - ✅ 프롬프트 파일 로드 성공

    📊 분류기 상태:
        llm_initialized: True
        prompt_loaded: True
        model: openai/gpt-4o-mini
        api_configured: True
        project_root: ***/flownote-mvp
        classifier_dir: ***/flownote-mvp/backend/classifier/

    ======================================================================
    분류 테스트 실행
    ======================================================================

    📝 테스트 1:
    입력: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다. 프로젝트 진행 상황을 공유하고 새로운 ...
    2025-11-02 12:40:12,178 - __main__ - ERROR - ❌ 오류: KeyError: '\n  "tags"'
    2025-11-02 12:40:12,178 - __main__ - INFO - 🔄 Fallback 분류: ['업무', '학습'], confidence: 0.95
    ✅ 태그: ['업무', '학습']
    📊 신뢰도: 0.95
    🔑 키워드: {'업무': ['회의', '프로젝트'], '학습': ['학습', '스터디']}

    📝 테스트 2:
    입력: 일기를 쓰면서 오늘 하루를 돌아봅니다. 감정을 정리하고 내일 할 일을 생각해봤습니다....
    2025-11-02 12:40:12,178 - __main__ - ERROR - ❌ 오류: KeyError: '\n  "tags"'
    2025-11-02 12:40:12,178 - __main__ - INFO - 🔄 Fallback 분류: ['개인'], confidence: 0.85
    ✅ 태그: ['개인']
    📊 신뢰도: 0.85
    🔑 키워드: {'개인': ['일기', '생각', '감정']}

    📝 테스트 3:
    입력: 오늘 헬스장에 가서 운동했습니다. PT 세션도 받고 식단 상담도 받았어요....
    2025-11-02 12:40:12,178 - __main__ - ERROR - ❌ 오류: KeyError: '\n  "tags"'
    2025-11-02 12:40:12,178 - __main__ - INFO - 🔄 Fallback 분류: ['건강'], confidence: 0.85
    ✅ 태그: ['건강']
    📊 신뢰도: 0.85
    🔑 키워드: {'건강': ['운동', '헬스', '식단']}

"""


"""test_result_3 → 🔼

    `python backend/classifier/keyword_classifier.py - metadata_prompts 파일 재검토 및 수정 필요`

    ======================================================================
    KeywordClassifier 테스트
    ======================================================================
    2025-11-02 12:49:20,298 - __main__ - INFO - ✅ KeywordClassifier LLM 초기화 성공 (gpt-4o-mini)
    2025-11-02 12:49:20,299 - __main__ - INFO - ✅ 프롬프트 파일 로드 성공

    📊 분류기 상태:
        llm_initialized: True
        prompt_loaded: True
        model: openai/gpt-4o-mini
        api_configured: True
        project_root: /Users/jay/ICT-projects/flownote-mvp
        classifier_dir: /Users/jay/ICT-projects/flownote-mvp/backend/classifier

    ======================================================================
    분류 테스트 실행
    ======================================================================

    📝 테스트 1:
    입력: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다. 프로젝트 진행 상황을 공유하고 새로운 ...
    2025-11-02 12:49:20,299 - __main__ - ERROR - ❌ 오류: KeyError: '\n  "tags"'
    2025-11-02 12:49:20,299 - __main__ - INFO - 🔄 Fallback 분류: ['업무', '학습'], confidence: 0.95
    ✅ 태그: ['업무', '학습']
    📊 신뢰도: 0.95
    🔑 키워드: {'업무': ['회의', '프로젝트'], '학습': ['학습', '스터디']}

    📝 테스트 2:
    입력: 일기를 쓰면서 오늘 하루를 돌아봅니다. 감정을 정리하고 내일 할 일을 생각해봤습니다....
    2025-11-02 12:49:20,299 - __main__ - ERROR - ❌ 오류: KeyError: '\n  "tags"'
    2025-11-02 12:49:20,299 - __main__ - INFO - 🔄 Fallback 분류: ['개인'], confidence: 0.85
    ✅ 태그: ['개인']
    📊 신뢰도: 0.85
    🔑 키워드: {'개인': ['일기', '생각', '감정']}

    📝 테스트 3:
    입력: 오늘 헬스장에 가서 운동했습니다. PT 세션도 받고 식단 상담도 받았어요....
    2025-11-02 12:49:20,299 - __main__ - ERROR - ❌ 오류: KeyError: '\n  "tags"'
    2025-11-02 12:49:20,299 - __main__ - INFO - 🔄 Fallback 분류: ['건강'], confidence: 0.85
    ✅ 태그: ['건강']
    📊 신뢰도: 0.85
    🔑 키워드: {'건강': ['운동', '헬스', '식단']}


"""


"""test_result_4 → 🔼

    `로직 수정 → 이스케이프 문제 여전히 발생`

    ======================================================================
    KeywordClassifier 테스트
    ======================================================================
    2025-11-02 13:49:01,490 - INFO - ✅ KeywordClassifier LLM 초기화 성공
    2025-11-02 13:49:01,491 - INFO - ✅ 프롬프트 로드 및 Chain 생성 성공

    📊 분류기 상태:
        llm_initialized: True
        chain_initialized: True
        model: openai/gpt-4o-mini
        api_configured: True

    ======================================================================
    분류 테스트
    ======================================================================

    📝 테스트 1: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다.
    2025-11-02 13:49:01,491 - INFO - 🚀 LLM 호출 시작: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다....
    2025-11-02 13:49:01,492 - ERROR - ❌ 분류 오류: KeyError: 'Input to ChatPromptTemplate is missing variables {\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\'}.  Expected: [\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\', \'text\'] Received: [\'text\']\nNote: if you intended {} to be part of the string and not a variable, please escape it with double curly braces like: \'{{}}\'.\nFor troubleshooting, visit: https://python.langchain.com/docs/troubleshooting/errors/INVALID_PROMPT_INPUT '
    2025-11-02 13:49:01,492 - ERROR - 상세 에러: 'Input to ChatPromptTemplate is missing variables {\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\'}.  Expected: [\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\', \'text\'] Received: [\'text\']\nNote: if you intended {} to be part of the string and not a variable, please escape it with double curly braces like: \'{{}}\'.\nFor troubleshooting, visit: https://python.langchain.com/docs/troubleshooting/errors/INVALID_PROMPT_INPUT '
    2025-11-02 13:49:01,492 - INFO - 🔄 Fallback 분류: ['업무', '학습']
    ✅ 태그: ['업무', '학습']
    📊 신뢰도: 0.65
    🔑 키워드: {'업무': ['회의'], '학습': ['스터디']}

    📝 테스트 2: 일기를 쓰면서 오늘 하루를 돌아봅니다.
    2025-11-02 13:49:01,492 - INFO - 🚀 LLM 호출 시작: 일기를 쓰면서 오늘 하루를 돌아봅니다....
    2025-11-02 13:49:01,492 - ERROR - ❌ 분류 오류: KeyError: 'Input to ChatPromptTemplate is missing variables {\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\'}.  Expected: [\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\', \'text\'] Received: [\'text\']\nNote: if you intended {} to be part of the string and not a variable, please escape it with double curly braces like: \'{{}}\'.\nFor troubleshooting, visit: https://python.langchain.com/docs/troubleshooting/errors/INVALID_PROMPT_INPUT '
    2025-11-02 13:49:01,492 - ERROR - 상세 에러: 'Input to ChatPromptTemplate is missing variables {\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\'}.  Expected: [\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\', \'text\'] Received: [\'text\']\nNote: if you intended {} to be part of the string and not a variable, please escape it with double curly braces like: \'{{}}\'.\nFor troubleshooting, visit: https://python.langchain.com/docs/troubleshooting/errors/INVALID_PROMPT_INPUT '
    2025-11-02 13:49:01,492 - INFO - 🔄 Fallback 분류: ['개인']
    ✅ 태그: ['개인']
    📊 신뢰도: 0.3
    🔑 키워드: {'개인': ['일기']}

    📝 테스트 3: 오늘 헬스장에 가서 운동했습니다.
    2025-11-02 13:49:01,492 - INFO - 🚀 LLM 호출 시작: 오늘 헬스장에 가서 운동했습니다....
    2025-11-02 13:49:01,493 - ERROR - ❌ 분류 오류: KeyError: 'Input to ChatPromptTemplate is missing variables {\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\'}.  Expected: [\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\', \'text\'] Received: [\'text\']\nNote: if you intended {} to be part of the string and not a variable, please escape it with double curly braces like: \'{{}}\'.\nFor troubleshooting, visit: https://python.langchain.com/docs/troubleshooting/errors/INVALID_PROMPT_INPUT '
    2025-11-02 13:49:01,493 - ERROR - 상세 에러: 'Input to ChatPromptTemplate is missing variables {\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\'}.  Expected: [\'\', \'\\n        "keyword_count"\', \'\\n  "tags"\', \'text\'] Received: [\'text\']\nNote: if you intended {} to be part of the string and not a variable, please escape it with double curly braces like: \'{{}}\'.\nFor troubleshooting, visit: https://python.langchain.com/docs/troubleshooting/errors/INVALID_PROMPT_INPUT '
    2025-11-02 13:49:01,493 - INFO - 🔄 Fallback 분류: ['건강']
    ✅ 태그: ['건강']
    📊 신뢰도: 0.65
    🔑 키워드: {'건강': ['운동', '헬스']}

"""


"""test_result_5 → ⭕️

    ======================================================================
    KeywordClassifier 테스트
    ======================================================================
    2025-11-02 13:52:49,371 - INFO - ✅ KeywordClassifier LLM 초기화 성공
    2025-11-02 13:52:49,372 - INFO - ✅ 프롬프트 로드 및 Chain 생성 성공

    📊 분류기 상태:
        llm_initialized: True
        chain_initialized: True
        model: openai/gpt-4o-mini
        api_configured: True

    ======================================================================
    분류 테스트
    ======================================================================

    📝 테스트 1: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다.
    2025-11-02 13:52:49,372 - INFO - 🚀 LLM 호출 시작: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다....
    2025-11-02 13:52:51,916 - INFO - HTTP Request: POST https://*** "HTTP/1.1 200 OK"

    ================================================================================
    🔍 원본 LLM 응답:
    ================================================================================
    {
        "tags": ["업무", "학습"],
        "confidence": 0.85,
        "matched_keywords": {
            "업무": ["회의"],
            "학습": ["스터디"]
            },
        "reasoning": "업무 관련 회의와 학습 관련 스터디 키워드가 출현하여 두 카테고리에 해당됨",
        "para_hints": {
            "업무": ["Projects"],
            "학습": ["Areas"]
        }
    }
    ================================================================================

    📄 추출된 JSON:
    {
        "tags": ["업무", "학습"],
        "confidence": 0.85,
        "matched_keywords": {
            "업무": ["회의"],
            "학습": ["스터디"]
            },
        "reasoning": "업무 관련 회의와 학습 관련 스터디 키워드가 출현하여 두 카테고리에 해당됨",
        "para_hints": {
            "업무": ["Projects"],
            "학습": ["Areas"]
        }
    }

    2025-11-02 13:52:51,925 - INFO - ✅ LLM 분류 성공: ['업무', '학습']
    ✅ 태그: ['업무', '학습']
    📊 신뢰도: 0.85
    🔑 키워드: {'업무': ['회의'], '학습': ['스터디']}

    📝 테스트 2: 일기를 쓰면서 오늘 하루를 돌아봅니다.
    2025-11-02 13:52:51,926 - INFO - 🚀 LLM 호출 시작: 일기를 쓰면서 오늘 하루를 돌아봅니다....
    2025-11-02 13:52:51,916 - INFO - HTTP Request: POST https://*** "HTTP/1.1 200 OK"

    ================================================================================
    🔍 원본 LLM 응답:
    ================================================================================
    {
        "tags": ["개인"],
        "confidence": 0.85,
        "matched_keywords": {
            "개인": ["일기", "회고"]
        },
        "reasoning": "개인적 기록과 하루를 돌아보는 감정 정리에 해당하는 키워드가 명확함",
        "para_hints": {
            "개인": ["Resources"]
        }
    }
    ================================================================================

    📄 추출된 JSON:
    {
        "tags": ["개인"],
        "confidence": 0.85,
        "matched_keywords": {
            "개인": ["일기", "회고"]
        },
        "reasoning": "개인적 기록과 하루를 돌아보는 감정 정리에 해당하는 키워드가 명확함",
        "para_hints": {
            "개인": ["Resources"]
        }
    }

    2025-11-02 13:52:54,244 - INFO - ✅ LLM 분류 성공: ['개인']
    ✅ 태그: ['개인']
    📊 신뢰도: 0.85
    🔑 키워드: {'개인': ['일기', '회고']}

    📝 테스트 3: 오늘 헬스장에 가서 운동했습니다.
    2025-11-02 13:52:54,244 - INFO - 🚀 LLM 호출 시작: 오늘 헬스장에 가서 운동했습니다....
    2025-11-02 13:52:51,916 - INFO - HTTP Request: POST https://*** "HTTP/1.1 200 OK"

    ================================================================================
    🔍 원본 LLM 응답:
    ================================================================================
    {
        "tags": ["건강"],
        "confidence": 0.85,
        "matched_keywords": {
            "건강": ["헬스장", "운동"]
            },
        "reasoning": "운동 관련 키워드가 명확히 감지되어 건강 카테고리에 해당됨",
        "para_hints": {
            "건강": ["Areas"]
        }
    }
    ================================================================================

    📄 추출된 JSON:
    {
        "tags": ["건강"],
        "confidence": 0.85,
        "matched_keywords": {
            "건강": ["헬스장", "운동"]
            },
        "reasoning": "운동 관련 키워드가 명확히 감지되어 건강 카테고리에 해당됨",
        "para_hints": {
            "건강": ["Areas"]
        }
    }

    2025-11-02 13:52:56,918 - INFO - ✅ LLM 분류 성공: ['건강']
    ✅ 태그: ['건강']
    📊 신뢰도: 0.85
    🔑 키워드: {'건강': ['헬스장', '운동']}

"""
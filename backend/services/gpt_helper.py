# backend/services/gpt_helper.py

"""
🤖 GPT-4o 헬퍼 클래스
기존 config.py를 활용한 재사용 가능한 GPT 호출 유틸리티
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import os
from dotenv import load_dotenv

# 로컬 .env 로드
load_dotenv()

# Streamlit Secrets (배포용)
try:
    import streamlit as st
    if hasattr(st, 'secrets') and len(st.secrets) > 0:
        for key in ["GPT4O_API_KEY", "GPT4O_BASE_URL", ...]:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
except:
    pass

from backend.config import ModelConfig

import re
import json
import logging
from typing import Dict, List, Optional
from backend.config import ModelConfig

logger = logging.getLogger(__name__)


class GPT4oHelper:
    """
    GPT-4o 전용 헬퍼 클래스
    
    기능:
    - suggest_areas: 직업별 책임 영역 추천
    - generate_keywords: 영역별 키워드 생성
    - classify_text: 간단한 텍스트 분류
    """
    
    def __init__(self):
        """초기화: GPT-4o 클라이언트 생성"""
        try:
            self.client = ModelConfig.get_openai_client("gpt-4o")
            self.model = ModelConfig.GPT4O_MODEL
            logger.info("✅ GPT-4o 클라이언트 초기화 성공")
        except Exception as e:
            logger.error(f"❌ GPT-4o 초기화 실패: {e}")
            self.client = None
            self.model = None
    
    def _call(self, prompt: str, system_prompt: str = None, max_tokens: int = 500) -> str:
        """
        GPT-4o 호출 (내부 메서드)
        
        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트
            max_tokens: 최대 토큰
            
        Returns:
            GPT-4o 응답 텍스트
        """
        if not self.client:
            raise Exception("GPT-4o 클라이언트가 초기화되지 않았습니다")
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        # ✨ 정규표현식으로 한방에 제거!
        # 1. 시작 부분의 마크다운 코드 블록 마커 제거 (```json 또는 ```)
        raw_response = re.sub(r'^```(?:json)?\n', '', raw_response)
        # 2. 끝 부분의 마크다운 코드 블록 마커 제거 (```)
        # 마지막에 ```가 있는 경우에만 제거하도록 $ 앵커를 추가하는 것이 안전
        raw_response = re.sub(r'\n```$', '', raw_response)
        
        logger.info(f"🔍 CLEANED RESPONSE: {raw_response[:200]}")           # ← 처음 200자 출력!
        logger.info(f"📏 RESPONSE LENGTH: {len(raw_response)}")             # ← 길이 확인!
        
        return raw_response
    
    # ============================================
    # 🎯 핵심 기능 1: 직업별 영역 추천
    # ============================================
    
    def _load_prompt(self, prompt_name: str) -> str:
        """
        prompts/ 폴더에서 프롬프트 파일 로드
        
        Args:
            prompt_name: 프롬프트 파일명 (확장자 제외)
            
        Returns:
            프롬프트 내용
        """
        from pathlib import Path
        
        prompt_path = Path(__file__).parent.parent / "classifier" / "prompts" / f"{prompt_name}.txt"
        
        if not prompt_path.exists():
            logger.warning(f"⚠️ 프롬프트 파일 없음: {prompt_path}")
            return ""
        
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    
    def suggest_areas(self, occupation: str, count: int = 5) -> Dict[str, any]:
        """
        직업에 맞는 책임 영역 추천
        
        Args:
            occupation: 직업 (예: "교사", "개발자")
            count: 추천할 영역 개수
            
        Returns:
            {
                "status": "success" | "error",
                "areas": ["영역1", "영역2", ...],
                "message": "설명"
            }
        """
        try:
            # ✅ prompts/에서 시스템 프롬프트 로드 시도
            system_prompt = self._load_prompt("onboarding_suggest_areas")
            
            # ✅ 프롬프트 없으면 기본값 사용
            if not system_prompt:
                logger.warning("⚠️ 프롬프트 파일 없음, 기본 프롬프트 사용")
                system_prompt = """
당신은 직업별 핵심 책임 영역을 추천하는 전문가입니다.
각 영역은 3-5단어로 간결하게 표현하세요.
반드시 JSON 형식으로만 응답하세요.
                """.strip()
            
            user_prompt = f"""
직업: {occupation}

이 직업의 사람이 책임지고 관리해야 하는 핵심 영역을 {count}개 추천해주세요.

출력 형식 (JSON만):
{{
  "areas": ["영역1", "영역2", "영역3", "영역4", "영역5"]
}}
            """.strip()
            
            # GPT-4o 호출
            response = self._call(user_prompt, system_prompt)
            
            # JSON 파싱
            result = json.loads(response)
            areas = result.get("areas", [])
            
            logger.info(f"✅ GPT-4o 영역 추천 성공: {occupation} → {len(areas)}개")
            
            return {
                "status": "success",
                "areas": areas,
                "message": f"{occupation}의 핵심 영역 {len(areas)}개 추천됨"
            }
        
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 파싱 실패: {e}")
            # Fallback
            return {
                "status": "success",
                "areas": self._get_fallback_areas(occupation, count),
                "message": "기본 추천값 (GPT 파싱 실패)"
            }
        
        except Exception as e:
            logger.error(f"❌ GPT-4o 호출 실패: {e}")
            return {
                "status": "error",
                "areas": self._get_fallback_areas(occupation, count),
                "message": f"오류: {str(e)}"
            }




    def _get_fallback_areas(self, occupation: str, count: int = 5) -> List[str]:
        """
        Fallback: 하드코딩된 직업별 영역
        """
        fallback_map = {
            "교사": ["학생 평가", "수업 계획", "학급 운영", "학부모 소통", "교사 연수"],
            "개발자": ["코드 리뷰", "아키텍처 설계", "팀 협업", "기술 학습", "프로젝트 관리"],
            "마케터": ["캠페인 전략", "고객 분석", "브랜드 관리", "데이터 분석", "시장 조사"],
            "학생": ["시험 준비", "과제 관리", "동아리 활동", "진로 탐색", "공부 습관"],
        }
        
        return fallback_map.get(occupation, [f"관심분야{i+1}" for i in range(count)])
    
    # ============================================
    # 🎯 핵심 기능 2: 영역별 키워드 생성
    # ============================================
    
    def generate_keywords(self, occupation: str, areas: List[str]) -> Dict[str, List[str]]:
        """
        각 영역별 핵심 키워드 생성
        
        Args:
            occupation: 직업
            areas: 영역 목록
            
        Returns:
            {
                "영역1": ["키워드1", "키워드2", ...],
                "영역2": ["키워드3", "키워드4", ...],
                ...
            }
        """
        try:
            system_prompt = """
당신은 영역별 핵심 키워드를 추출하는 전문가입니다.
각 영역마다 3-5개의 키워드를 제시하세요.
반드시 JSON 형식으로만 응답하세요.
            """.strip()
            
            user_prompt = f"""
직업: {occupation}
영역: {', '.join(areas)}

각 영역별로 핵심 키워드 3-5개를 추출하세요.

출력 형식 (JSON만):
{{
  "영역1": ["키워드1", "키워드2", "키워드3"],
  "영역2": ["키워드4", "키워드5", "키워드6"],
  ...
}}
            """.strip()
            
            response = self._call(user_prompt, system_prompt, max_tokens=800)
            result = json.loads(response)
            
            logger.info(f"✅ 키워드 생성 성공: {len(result)}개 영역")
            return result
        
        except Exception as e:
            logger.error(f"❌ 키워드 생성 실패: {e}")
            # Fallback
            return {area: [f"{area}_키워드{i+1}" for i in range(3)] for area in areas}
    
    # ============================================
    # 🎯 핵심 기능 3: 간단한 텍스트 분류
    # ============================================
    
    def classify_text(self, text: str, categories: List[str]) -> Dict[str, any]:
        """
        텍스트를 주어진 카테고리로 분류
        
        Args:
            text: 분류할 텍스트
            categories: 카테고리 목록
            
        Returns:
            {
                "status": "success",
                "category": "선택된 카테고리",
                "confidence": 0.95,
                "reasoning": "분류 이유"
            }
        """
        try:
            system_prompt = """
당신은 텍스트 분류 전문가입니다.
주어진 카테고리 중 가장 적합한 것을 선택하세요.
반드시 JSON 형식으로만 응답하세요.
            """.strip()
            
            user_prompt = f"""
텍스트: {text}
카테고리: {', '.join(categories)}

가장 적합한 카테고리를 선택하고, 신뢰도(0-1)와 이유를 제시하세요.

출력 형식 (JSON만):
{{
  "category": "선택된 카테고리",
  "confidence": 0.95,
  "reasoning": "분류 이유 (한국어)"
}}
            """.strip()
            
            response = self._call(user_prompt, system_prompt)
            result = json.loads(response)
            
            return {
                "status": "success",
                **result
            }
        
        except Exception as e:
            logger.error(f"❌ 텍스트 분류 실패: {e}")
            return {
                "status": "error",
                "category": categories[0] if categories else "Unknown",
                "confidence": 0.5,
                "reasoning": f"오류: {str(e)}"
            }


# ============================================
# 싱글톤 인스턴스 (선택사항)
# ============================================

_gpt_helper_instance: Optional[GPT4oHelper] = None

def get_gpt_helper() -> GPT4oHelper:
    """GPT4oHelper 싱글톤 반환"""
    global _gpt_helper_instance
    
    if _gpt_helper_instance is None:
        _gpt_helper_instance = GPT4oHelper()
    
    return _gpt_helper_instance


# ============================================
# 테스트 코드
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*60)
    print("🤖 GPT-4o Helper 테스트")
    print("="*60)
    
    helper = GPT4oHelper()
    
    # 테스트 1: 영역 추천
    print("\n[테스트 1] 직업별 영역 추천")
    result = helper.suggest_areas("교사")
    print(f"상태: {result['status']}")
    print(f"영역: {result['areas']}")
    print(f"메시지: {result['message']}")
    
    # 테스트 2: 키워드 생성
    print("\n[테스트 2] 영역별 키워드 생성")
    keywords = helper.generate_keywords("교사", result['areas'][:3])
    for area, kws in keywords.items():
        print(f"  {area}: {', '.join(kws)}")
    
    # 테스트 3: 텍스트 분류
    print("\n[테스트 3] 텍스트 분류")
    classify_result = helper.classify_text(
        "2025년 수업 계획서 작성",
        ["Projects", "Areas", "Resources", "Archives"]
    )
    print(f"카테고리: {classify_result['category']}")
    print(f"신뢰도: {classify_result['confidence']}")
    print(f"이유: {classify_result['reasoning']}")
    
    print("\n" + "="*60)
    print("🤖 GPT-4o Helper 수정 테스트 완료")
    print("="*60)


"""test_result_1 - ❌

    ➀ curl "http://localhost:8000/api/onboarding/suggest-areas?user_id=test&occupation=교사" | jq '.'

    % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                    Dload  Upload   Total   Spent    Left  Speed
    100    30    0    30    0     0  22988      0 --:--:-- --:--:-- --:--:-- 30000
    jq: parse error: Invalid numeric literal at line 1, column 8

    ➁ python -m backend.services.gpt_helper

    ============================================================
    🤖 GPT-4o Helper 테스트
    ============================================================
    INFO:__main__:✅ GPT-4o 클라이언트 초기화 성공

    [테스트 1] 직업별 영역 추천
    INFO:httpx:HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    ERROR:__main__:❌ JSON 파싱 실패: Expecting value: line 1 column 1 (char 0)
        상태: success
        영역: ['학생 평가', '수업 계획', '학급 운영', '학부모 소통', '교사 연수']
        메시지: 기본 추천값 (GPT 파싱 실패)

    [테스트 2] 영역별 키워드 생성
    INFO:httpx:HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    ERROR:__main__:❌ 키워드 생성 실패: Expecting value: line 1 column 1 (char 0)
        학생 평가: 학생 평가_키워드1, 학생 평가_키워드2, 학생 평가_키워드3
        수업 계획: 수업 계획_키워드1, 수업 계획_키워드2, 수업 계획_키워드3
        학급 운영: 학급 운영_키워드1, 학급 운영_키워드2, 학급 운영_키워드3

    [테스트 3] 텍스트 분류
    INFO:httpx:HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    카테고리: Projects
    신뢰도: 0.9
    이유: 수업 계획서는 특정한 목표와 결과를 염두에 두고 작성되는 문서로, 일정에 따라 수행해야 할 작업을 포함합니다. 이는 프로젝트의 특성과 유사하여 'Projects' 카테고리에 가장 적합합니다.

    ============================================================
    🤖 GPT-4o Helper 테스트 완료

    → JSON 파싱 실패: 응답이 그냥 텍스트 (JSON 아님) ← 이게 가장 가능성 높음!
    → 프록시 문제 → JSON 대신 다른 형식 반환하는 것일수도 있음
    → 디버깅 코드 추가하기 

"""


"""test_result_2 → ❌

    ```python
    # def _call(self, prompt: str, system_prompt: str = None, max_tokens: int = 500) -> str:
    
        # ✨ 마크다운 코드 블록 제거!
        if raw_response.startswith("```json"):
            raw_response = raw_response.replace("``````", "")
        elif raw_response.startswith("```"):
            raw_response = raw_response.replace("```\n", "").replace("\n```", "")
        
        logger.info(f"🔍 CLEANED RESPONSE: {raw_response[:200]}")           # ← 처음 200자 출력!
        logger.info(f"📏 RESPONSE LENGTH: {len(raw_response)}")             # ← 길이 확인!
    ```
    
    python -m backend.services.gpt_helper

    ============================================================
    🤖 GPT-4o Helper 테스트
    ============================================================
    INFO:__main__:✅ GPT-4o 클라이언트 초기화 성공

    [테스트 1] 직업별 영역 추천
    INFO:httpx:HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    ERROR:__main__:❌ GPT-4o 호출 실패: 'list' object has no attribute 'message'
    상태: error
    영역: ['학생 평가', '수업 계획', '학급 운영', '학부모 소통', '교사 연수']
    메시지: 오류: 'list' object has no attribute 'message'

    [테스트 2] 영역별 키워드 생성
    INFO:httpx:HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    ERROR:__main__:❌ 키워드 생성 실패: 'list' object has no attribute 'message'
    학생 평가: 학생 평가_키워드1, 학생 평가_키워드2, 학생 평가_키워드3
    수업 계획: 수업 계획_키워드1, 수업 계획_키워드2, 수업 계획_키워드3
    학급 운영: 학급 운영_키워드1, 학급 운영_키워드2, 학급 운영_키워드3

    [테스트 3] 텍스트 분류
    INFO:httpx:HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    ERROR:__main__:❌ 텍스트 분류 실패: 'list' object has no attribute 'message'
    카테고리: Projects
    신뢰도: 0.5
    이유: 오류: 'list' object has no attribute 'message'

    ============================================================
    🤖 GPT-4o Helper 테스트 완료
    ============================================================

"""


"""test_result_3 → ❌

    ➀ python -m backend.services.gpt_helper

    ```python
    # def _call(self, prompt: str, system_prompt: str = None, max_tokens: int = 500) -> str:
    
        # ✨ 정규표현식으로 한방에 제거!
        # 1. 시작 부분의 마크다운 코드 블록 마커 제거 (```json 또는 ```)
        raw_response = re.sub(r'^```(?:json)?\n', '', raw_response)
        # 2. 끝 부분의 마크다운 코드 블록 마커 제거 (```)
        # 마지막에 ```가 있는 경우에만 제거하도록 $ 앵커를 추가하는 것이 안전
        raw_response = re.sub(r'\n```$', '', raw_response)
        
        logger.info(f"🔍 CLEANED RESPONSE: {raw_response[:200]}")           # ← 처음 200자 출력!
        logger.info(f"📏 RESPONSE LENGTH: {len(raw_response)}")             # ← 길이 확인!
        
        return raw_response
    
    ```


    ============================================================
    🤖 GPT-4o Helper 테스트
    ============================================================
    INFO:__main__:✅ GPT-4o 클라이언트 초기화 성공

    [테스트 1] 직업별 영역 추천
    INFO:httpx:HTTP Request: POST https://mlapi.run/0e6857e3-a90b-4c99-93ac-1f9f887a193e/v1/chat/completions "HTTP/1.1 200 OK"
    INFO:__main__:🔍 CLEANED RESPONSE: ```json
    {
    "areas": ["교과목 교육", "학생 평가", "수업 계획", "학급 관리", "부모 소통"]
    }
    ```
    INFO:__main__:📏 RESPONSE LENGTH: 73
    ERROR:__main__:❌ JSON 파싱 실패: Expecting value: line 1 column 1 (char 0)
    상태: success
    영역: ['학생 평가', '수업 계획', '학급 운영', '학부모 소통', '교사 연수']
    메시지: 기본 추천값 (GPT 파싱 실패)

    [테스트 2] 영역별 키워드 생성
    INFO:httpx:HTTP Request: POST https://mlapi.run/0e6857e3-a90b-4c99-93ac-1f9f887a193e/v1/chat/completions "HTTP/1.1 200 OK"
    INFO:__main__:🔍 CLEANED RESPONSE: ```json
    {
    "학생 평가": ["성취도", "평가 기준", "피드백", "객관성", "개별화"],
    "수업 계획": ["학습 목표", "교수법", "교육 자료", "커리큘럼", "차시별 계획"],
    "학급 운영": ["학급 관리", "규칙 설정", "학생 참여", "소통", "안전"]
    }
    ```
    INFO:__main__:📏 RESPONSE LENGTH: 172
    ERROR:__main__:❌ 키워드 생성 실패: Expecting value: line 1 column 1 (char 0)
    학생 평가: 학생 평가_키워드1, 학생 평가_키워드2, 학생 평가_키워드3
    수업 계획: 수업 계획_키워드1, 수업 계획_키워드2, 수업 계획_키워드3
    학급 운영: 학급 운영_키워드1, 학급 운영_키워드2, 학급 운영_키워드3

    [테스트 3] 텍스트 분류
    INFO:httpx:HTTP Request: POST https://mlapi.run/0e6857e3-a90b-4c99-93ac-1f9f887a193e/v1/chat/completions "HTTP/1.1 200 OK"
    INFO:__main__:🔍 CLEANED RESPONSE: ```json
    {
    "category": "Projects",
    "confidence": 0.9,
    "reasoning": "수업 계획서는 미래의 교육 활동을 위한 구체적인 계획을 세우는 문서로, 이는 프로젝트의 성격과 유사합니다. 따라서 '2025년 수업 계획서 작성'은 특정 목표를 달성하기 위한 계획이므로 'Projects' 카테고리가 적합합니다.
    INFO:__main__:📏 RESPONSE LENGTH: 207
    ERROR:__main__:❌ 텍스트 분류 실패: Expecting value: line 1 column 1 (char 0)
    카테고리: Projects
    신뢰도: 0.5
    이유: 오류: Expecting value: line 1 column 1 (char 0)
"""


"""test_result_4 → ⭕️
    ```python
    # def _call(self, prompt: str, system_prompt: str = None, max_tokens: int = 500) -> str:
    
        raw_response = response.choices[0].message.content.strip()      # ← [0] 추가
        # ✨ 정규표현식으로 한방에 제거!
    ```

    python -m backend.services.gpt_helper

    ============================================================
    🤖 GPT-4o Helper 테스트
    ============================================================
    INFO:__main__:✅ GPT-4o 클라이언트 초기화 성공

    [테스트 1] 직업별 영역 추천
    INFO:httpx:HTTP Request: POST https://mlapi.run/0e6857e3-a90b-4c99-93ac-1f9f887a193e/v1/chat/completions "HTTP/1.1 200 OK"
    INFO:__main__:🔍 CLEANED RESPONSE: {
    "areas": ["수업 계획", "학생 평가", "교실 관리", "상담 지도", "교과 연구"]
    }
    INFO:__main__:📏 RESPONSE LENGTH: 60
    INFO:__main__:✅ GPT-4o 영역 추천 성공: 교사 → 5개
    상태: success
    영역: ['수업 계획', '학생 평가', '교실 관리', '상담 지도', '교과 연구']
    메시지: 교사의 핵심 영역 5개 추천됨

    [테스트 2] 영역별 키워드 생성
    INFO:httpx:HTTP Request: POST https://mlapi.run/0e6857e3-a90b-4c99-93ac-1f9f887a193e/v1/chat/completions "HTTP/1.1 200 OK"
    INFO:__main__:🔍 CLEANED RESPONSE: {
    "수업 계획": ["학습 목표", "교재 선정", "시간 배분", "교육 자료", "수업 진행"],
    "학생 평가": ["시험", "과제", "참여도", "피드백", "성장 분석"],
    "교실 관리": ["규칙 설정", "환경 조성", "학생 참여", "문제 해결", "안전 관리"]
    }
    INFO:__main__:📏 RESPONSE LENGTH: 166
    INFO:__main__:✅ 키워드 생성 성공: 3개 영역
    수업 계획: 학습 목표, 교재 선정, 시간 배분, 교육 자료, 수업 진행
    학생 평가: 시험, 과제, 참여도, 피드백, 성장 분석
    교실 관리: 규칙 설정, 환경 조성, 학생 참여, 문제 해결, 안전 관리

    [테스트 3] 텍스트 분류
    INFO:httpx:HTTP Request: POST https://mlapi.run/0e6857e3-a90b-4c99-93ac-1f9f887a193e/v1/chat/completions "HTTP/1.1 200 OK"
    INFO:__main__:🔍 CLEANED RESPONSE: {
    "category": "Projects",
    "confidence": 0.9,
    "reasoning": "수업 계획서 작성은 미래의 특정 목표를 위한 계획 및 준비를 포함하는 작업으로, 프로젝트 성격이 강합니다. 따라서 'Projects' 카테고리가 가장 적합합니다."
    }
    INFO:__main__:📏 RESPONSE LENGTH: 158
    카테고리: Projects
    신뢰도: 0.9
    이유: 수업 계획서 작성은 미래의 특정 목표를 위한 계획 및 준비를 포함하는 작업으로, 프로젝트 성격이 강합니다. 따라서 'Projects' 카테고리가 가장 적합합니다.

    ============================================================
    🤖 GPT-4o Helper 테스트 완료
    ============================================================

"""


"""test_result_5 → 서버 테스트 ⭕️ 

    curl "http://localhost:8000/api/onboarding/suggest-areas?user_id=test&occupation=teacher"

    {
        "status":"success",
        "user_id":"test",
        "occupation":"teacher",
        "suggested_areas":[
            "관심분야1","관심분야2","관심분야3","관심분야4","관심분야5"
            ],
        "message":"Step 2: 아래 영역 중 관심있는 것을 선택하세요",
        "next_step":"/api/onboarding/save-context (POST with selected_areas)"
    }

    [서버 상태] python -m backend.main
    ✅ ModelConfig loaded from backend.config
    INFO:__main__:✅ api_router 등록 완료
    INFO:__main__:✅ classifier_router 등록 완료
    INFO:__main__:✅ onboarding_router 등록 완료
    INFO:__main__:🚀 FlowNote API 시작...
    INFO:__main__:📍 http://localhost:8000
    INFO:__main__:📚 문서: http://localhost:8000/docs
    INFO:     Started server process [97993]
    INFO:     Waiting for application startup.
    INFO:     Application startup complete.
    INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
    INFO:     127.0.0.1:59841 - "GET /api/onboarding/suggest-areas?user_id=test&occupation=teacher HTTP/1.1" 200 OK

"""








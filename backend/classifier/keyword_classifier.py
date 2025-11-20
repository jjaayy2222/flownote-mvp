# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/classifier/keyword_classifier.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
from typing import Dict, Any, Optional, List
import time
from datetime import datetime
import uuid

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
    """
    키워드 기반 분류기 (LLM 기반 - GPT-4o-mini)

    ✅ 특징:
    - 비동기/동기 메서드 모두 지원
    - 사용자 컨텍스트 완전 지원
    - UUID 기반 인스턴스 추적
    - 프롬프트 파일 그대로 사용 (모든 변수 전달하기)
    """

    def __init__(self):
        """KeywordClassifier 초기화"""

        # 고유 ID로 인스턴스 추적
        self.instance_id = str(uuid.uuid4())[:8]
        self.created_at = datetime.now().strftime("%H:%M:%S")

        self.llm = None
        self.chain = None
        self._initialize_llm()
        self._load_prompt()

        logger.info(
            f"✅ KeywordClassifier initialized (ID: {self.instance_id}, Time: {self.created_at})"
        )

    def _initialize_llm(self):
        """LLM 초기화 - 캐싱 없음"""
        try:
            # 매번 새로 연결하기
            api_key = ModelConfig.GPT4O_MINI_API_KEY

            if not api_key:
                raise ValueError("❌ GPT4O_MINI_API_KEY not set")

            self.llm = ChatOpenAI(
                api_key=api_key,
                base_url=ModelConfig.GPT4O_MINI_BASE_URL,
                model=ModelConfig.GPT4O_MINI_MODEL,
                temperature=0.7,
                max_tokens=600,
            )

            logger.info("✅ KeywordClassifier LLM 초기화 성공")

        except Exception as e:
            logger.error(f"❌ LLM 초기화 실패: {e}")
            self.llm = None

    def _load_prompt(self):
        """프롬프트 파일 로드 및 Chain 생성

        - 프롬프트 파일 그대로 사용하기
        - 템플릿 변수 모두 전달하기
        """
        try:
            prompt_path = (
                CLASSIFIER_DIR / "prompts" / "keyword_classification_prompt.txt"
            )

            if not prompt_path.exists():
                raise FileNotFoundError(f"프롬프트 파일 없음: {prompt_path}")

            with open(prompt_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            # 프롬프트 그대로 사용 (변수 이스케이프 처리)
            escaped_content = self._escape_prompt_braces(template_content)

            # ChatPromptTemplate 생성
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are a keyword extraction and classification expert. Always respond with valid JSON only.",
                    ),
                    ("user", escaped_content),
                ]
            )

            # Chain 생성: Prompt → LLM → StrOutputParser
            if self.llm:
                self.chain = prompt | self.llm | StrOutputParser()
                logger.info(
                    f"[{self.instance_id}] ✅ Chain 생성 성공 (프롬프트 파일 로드 완료)"
                )
            else:
                logger.warning(
                    f"[{self.instance_id}] ⚠️  LLM 미초기화로 Chain 생성 불가"
                )
        except Exception as e:
            logger.error(f"❌ 프롬프트 로드 실패: {e}")
            self.chain = None

    def _escape_prompt_braces(self, content: str) -> str:
        """
        프롬프트의 중괄호 이스케이프

        - {text}, {occupation}, {areas}, {interests}, {context_keywords} 변수 유지
        - 나머지 {}는 {{ }}로 이스케이프
        """
        # 템플릿 변수 목록
        template_vars = [
            "{text}",
            "{occupation}",
            "{areas}",
            "{interests}",
            "{context_keywords}",
        ]

        lines = []

        for line in content.split("\n"):

            # 템플릿 변수가 있는 라인은 그대로 유지
            if any(var in line for var in template_vars):
                lines.append(line)
            else:
                # 나머지 라인의 { } 를 {{ }} 로 변환
                # 단, 이미 이스케이프된 {{ }} 는 건드리지 않음
                escaped_line = line.replace("{", "{{").replace("}", "}}")
                # {{{{ → {{ 로 중복 이스케이프 방지
                escaped_line = escaped_line.replace("{{{{", "{{").replace("}}}}", "}}")
                lines.append(escaped_line)

        return "\n".join(lines)

    # 추가
    def _prepare_prompt_variables(
        self, text: str, user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """프롬프트 템플릿 변수 준비

        - 모든 변수를 문자열로 변환해서 전달!
        """
        # 기본값 설정
        occupation = "일반 사용자"
        areas = []
        interests = []
        context_keywords = {}

        # 사용자 컨텍스트에서 추출
        if user_context:
            occupation = user_context.get("occupation", "일반 사용자")
            areas = user_context.get("areas", [])
            interests = user_context.get("interests", [])

            # context_keywords 생성 (areas 기반)
            for area in areas:
                context_keywords[area] = [area, f"{area} 관련", f"{area} 업무"]

        # 모든 변수를 문자열로 변환하기
        return {
            "text": str(text[:1000]),  # 최대 1000자
            "occupation": str(occupation),
            "areas": ", ".join(areas) if areas else "없음",  # 리스트 → 문자열
            "interests": ", ".join(interests) if interests else "없음",
            "context_keywords": json.dumps(
                context_keywords, ensure_ascii=False
            ),  # dict → JSON 문자열
        }

    # ============================================================
    # 비동기 메서드 (FastAPI에서 사용!)
    # ============================================================
    async def aclassify(
        self, text: str, user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """텍스트 분류 (비동기 버전)

        - 모든 프롬프트 변수 전달 (context_keywords 포함!)
        - 비동기 LLM 호출
        - 구조화된 출력 파싱 (JSON)
        - 견고한 에러 핸들링
        """
        start_time = time.time()

        # 빈 텍스트 확인
        if not text or not text.strip():
            logger.warning(f"[{self.instance_id}] ⚠️  빈 텍스트 입력")
            return self._create_empty_response()

        # Chain 미초기화 확인
        if self.chain is None:
            logger.warning(f"[{self.instance_id}] ⚠️  Chain 미초기화, Fallback")
            return self._fallback_classify(text)

        try:
            # Step 1: 사용자 컨텍스트에서 키워드 생성
            context_keywords = []
            if user_context:
                # areas에서 키워드 추출
                if user_context.get("areas"):
                    context_keywords.extend(user_context["areas"])
                # interests에서 키워드 추출
                if user_context.get("interests"):
                    context_keywords.extend(user_context["interests"])

            # 중복 제거 및 문자열 변환
            context_keywords = list(set(context_keywords)) if context_keywords else []
            context_keywords_str = (
                ", ".join(context_keywords) if context_keywords else "없음"
            )

            # Step 2: 프롬프트 변수 준비 (모든 필수 변수 포함!)
            prompt_vars = {
                "text": text,
                "occupation": (
                    user_context.get("occupation", "일반 사용자")
                    if user_context
                    else "일반 사용자"
                ),
                "areas": (
                    ", ".join(user_context.get("areas", []))
                    if user_context and user_context.get("areas")
                    else "없음"
                ),
                "interests": (
                    ", ".join(user_context.get("interests", []))
                    if user_context and user_context.get("interests")
                    else "없음"
                ),
                "context_keywords": context_keywords_str,  # ✅ 누락된 변수 추가!
            }

            logger.info(f"[{self.instance_id}] 🔍 Calling LLM (async)...")
            logger.info(f"[{self.instance_id}]   - Text length: {len(text)}")
            logger.info(
                f"[{self.instance_id}]   - Occupation: {prompt_vars['occupation']}"
            )
            logger.info(f"[{self.instance_id}]   - Areas: {prompt_vars['areas']}")
            logger.info(
                f"[{self.instance_id}]   - Context Keywords: {prompt_vars['context_keywords']}"
            )

            # Step 3: 비동기 LLM 호출
            response = await self.chain.ainvoke(prompt_vars)

            # Step 4: 응답 타입 확인 및 로깅
            logger.info(f"[{self.instance_id}] 📦 RAW LLM Response:")
            logger.info(f"[{self.instance_id}]   - Type: {type(response)}")
            logger.info(
                f"[{self.instance_id}]   - Content preview: {str(response)[:200]}"
            )

            # Step 5: 응답 파싱 (타입에 따라 분기)
            if isinstance(response, dict):
                # 이미 dict 형태로 파싱된 경우 (StructuredOutputParser 사용 시)
                result = response
            elif isinstance(response, str):
                # 문자열 응답인 경우 JSON 파싱 시도
                json_text = self._extract_json_from_response(response)
                result = json.loads(json_text)
            else:
                # 기타 타입 (예: AIMessage)
                response_text = str(response)
                json_text = self._extract_json_from_response(response_text)
                result = json.loads(json_text)

            # Step 6: tags 필드 검증 및 정규화
            raw_tags = result.get("tags", [])
            logger.info(
                f"[{self.instance_id}] 📦 Extracted tags: {raw_tags} (type: {type(raw_tags)})"
            )

            if not raw_tags:
                # logger.warning(f"[{self.instance_id}] ⚠️  tags 없음, 기본값 설정")
                # 태그 없으면 텍스트에서 강제 추출
                logger.warning(
                    f"[{self.instance_id}] ⚠️  LLM이 빈 태그 반환, 강제 추출 시도"
                )
                raw_tags = self._extract_fallback_tags(text, user_context)

                # 타입 검증
                if isinstance(raw_tags, str):
                    raw_tags = [
                        tag.strip() for tag in raw_tags.split(",") if tag.strip()
                    ]

                # 최소 1개 보장
                final_tags = [
                    str(tag).strip() for tag in raw_tags if tag and str(tag).strip()
                ]
                if not final_tags:
                    final_tags = self._extract_fallback_tags(text, user_context)

                logger.info(f"[{self.instance_id}] ✅ 강제 추출 완료: (async):")
                logger.info(f"[{self.instance_id}]   - Tags: {final_tags}")
                logger.info(
                    f"[{self.instance_id}]   - Confidence: {result.get('confidence', 0.0)}"
                )

                return {
                    "tags": final_tags,
                    "confidence": result.get("confidence", 0.0),
                    "matched_keywords": result.get("matched_keywords", {}),
                    "reasoning": result.get("reasoning", ""),
                    "user_context_matched": result.get("user_context_matched", False),
                    "processing_time": f"{time.time() - start_time:.2f}s",
                    "instance_id": self.instance_id,
                }

            elif isinstance(raw_tags, str):
                # 문자열인 경우 리스트로 변환
                if "," in raw_tags:
                    tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
                else:
                    tags = [raw_tags.strip()] if raw_tags.strip() else ["기타"]
                logger.info(f"[{self.instance_id}] 🔄 문자열 → 리스트 변환: {tags}")

            elif isinstance(raw_tags, list):
                # 리스트 검증 및 정리
                tags = [
                    str(tag).strip() for tag in raw_tags if tag and str(tag).strip()
                ]
                if not tags:
                    tags = ["기타"]
                logger.info(f"[{self.instance_id}] ✅ 리스트 검증 완료: {len(tags)}개")
            else:
                logger.warning(
                    f"[{self.instance_id}] ⚠️  예상치 못한 타입: {type(raw_tags)}"
                )
                tags = ["기타"]

            # Step 7: confidence 검증
            confidence = result.get("confidence", 0.5)
            try:
                confidence = float(confidence)
                # 0~1 범위로 제한
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, TypeError):
                logger.warning(
                    f"[{self.instance_id}] ⚠️  잘못된 confidence 값: {confidence}"
                )
                confidence = 0.5

            # Step 8: 사용자 컨텍스트 매칭 확인
            user_context_matched = False
            if user_context and user_context.get("areas"):
                matched_areas = [
                    area
                    for area in user_context["areas"]
                    if any(area.lower() in tag.lower() for tag in tags)
                ]
                user_context_matched = len(matched_areas) > 0

            # Step 9: 최종 결과 조립
            processing_time = round(time.time() - start_time, 2)

            final_result = {
                "tags": tags,
                "confidence": confidence,
                "user_context_matched": user_context_matched,
                "user_areas": user_context.get("areas", []) if user_context else [],
                "instance_id": self.instance_id,
                "processing_time": f"{processing_time}s",
            }

            logger.info(f"[{self.instance_id}] ✅ 분류 완료 (async):")
            logger.info(f"[{self.instance_id}]   - Tags: {tags[:5]}")  # 처음 5개만 표시
            logger.info(f"[{self.instance_id}]   - Confidence: {confidence}")
            logger.info(f"[{self.instance_id}]   - Time: {processing_time}s")

            return final_result

        except json.JSONDecodeError as e:
            logger.error(f"[{self.instance_id}] ❌ JSON 파싱 실패: {e}")
            logger.error(
                f"[{self.instance_id}]   - Response preview: {str(response)[:500] if 'response' in locals() else 'N/A'}"
            )
            return self._fallback_classify(text)

        except Exception as e:
            logger.error(
                f"[{self.instance_id}] ❌ 분류 오류 (async): {type(e).__name__}: {e}",
                exc_info=True,
            )
            return self._fallback_classify(text)

    # ============================================================
    # 동기 메서드 (테스트용)
    # ============================================================
    def classify(
        self, text: str, user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """키워드 분류 (동기 버전)"""

        start_time = datetime.now()

        # 로그로 호출 추적
        logger.info(
            f"🔍 [{self.instance_id}] CLASSIFY 시작: text_len={len(text)}, has_context={bool(user_context)}"
        )

        # 빈 텍스트 확인
        if not text or not text.strip():
            logger.warning(f"[{self.instance_id}] ⚠️  빈 텍스트 입력")
            return self._create_empty_response()

        # Chain 미초기화 확인
        if self.chain is None:
            logger.warning(f"[{self.instance_id}] ⚠️  Chain 미초기화, Fallback")
            return self._fallback_classify(text)

        try:
            # 프롬프트 변수 준비
            prompt_vars = self._prepare_prompt_variables(text, user_context)
            logger.info(f"[{self.instance_id}] 🔍 Calling LLM (sync)...")

            # 동기 호출
            response_text = self.chain.invoke(prompt_vars)

            json_text = self._extract_json_from_response(response_text)
            result = json.loads(json_text)

            # tags 보장
            if "tags" not in result or not result["tags"]:
                result["tags"] = ["기타"]

            if "confidence" not in result:
                result["confidence"] = 0.5

            result["user_context_matched"] = bool(
                user_context and user_context.get("areas")
            )
            result["user_areas"] = user_context.get("areas", []) if user_context else []

            elapsed = (datetime.now() - start_time).total_seconds()
            result["processing_time"] = f"{elapsed:.2f}s"
            result["instance_id"] = self.instance_id

            logger.info(f"[{self.instance_id}] ✅ 분류 완료 (sync):")
            logger.info(f"[{self.instance_id}]   - Tags: {result.get('tags', [])}")

            return result

        except Exception as e:
            logger.error(f"[{self.instance_id}] ❌ 분류 오류 (sync): {e}")
            return self._fallback_classify(text)

    def _extract_json_from_response(self, response_text: str) -> str:
        """LLM 응답에서 JSON 추출"""
        response_text = response_text.strip()

        # Step 1: ```json ... ``` 형식
        if "```json" in response_text:
            match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
            if match:
                return match.group(1).strip()

        # Step 2: ``` ... ``` 형식
        if "```" in response_text:
            match = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
            if match:
                return match.group(1).strip()

        # Step 3: { ... } JSON 객체 찾기
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if match:
            return match.group(0)

        # Step 4: 실패 - 전체 반환
        logger.warning(f"[{self.instance_id}] ⚠️  JSON 포맷 찾기 실패")
        return response_text

    def _fallback_classify(self, text: str) -> Dict[str, Any]:
        """Fallback 분류 (LLM 실패 시)

        간단한 키워드 매칭으로 대체
        """

        logger.info(f"[{self.instance_id}] 🔄 Fallback 분류 시작...")

        try:
            # 텍스트 정규화
            normalized_text = text.lower()

            # 기본 키워드 사전 (예시)
            keyword_dict = {
                "개발": ["개발", "코드", "프로그래밍", "api", "버그", "디버깅"],
                "디자인": ["디자인", "ui", "ux", "figma", "색상", "레이아웃"],
                "회의": ["회의", "미팅", "논의", "결정", "안건"],
                "기획": ["기획", "전략", "계획", "목표", "방향성"],
                "마케팅": ["마케팅", "광고", "홍보", "캠페인", "고객"],
                "데이터": ["데이터", "분석", "통계", "차트", "지표"],
            }

            # 키워드 매칭
            matched_dict = {}

            for category, keywords in keyword_dict.items():
                match_count = sum(1 for kw in keywords if kw in normalized_text)
                if match_count > 0:
                    matched_dict[category] = match_count

            # 점수 기준 정렬 및 상위 3개 선택
            if matched_dict:
                sorted_categories = sorted(
                    matched_dict.items(), key=lambda x: x[1], reverse=True
                )
                tags = [
                    cat for cat, _ in sorted_categories[:3]
                ]  # 수정: dict_keys 슬라이싱 오류 해결
                confidence = 0.3  # Fallback이므로 낮은 신뢰도
            else:
                tags = ["기타"]
                confidence = 0.1

            logger.info(f"[{self.instance_id}] 🔄 Fallback 분류: {tags}")

            return {
                "tags": tags,  # 항상 존재
                "confidence": confidence,  # 신뢰도
                "user_context_matched": False,
                "user_areas": [],
                "matched_keywords": matched_dict,
                "instance_id": self.instance_id,
                "processing_time": "0.0s",
                "method": "fallback",
                # "para_hints": {},
                # "is_fallback": True,
            }

        except Exception as e:
            logger.error(f"[{self.instance_id}] ❌ Fallback 분류 실패: {e}")
            return {
                "tags": ["기타"],
                "confidence": 0.0,
                "user_context_matched": False,
                "user_areas": [],
                "instance_id": self.instance_id,
                "processing_time": "0.0s",
                "error": str(e),
            }

    def _extract_fallback_tags(
        self, text: str, user_context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """텍스트에서 태그 강제 추출 (Fallback)"""
        try:
            found_tags = []

            # 1. 사용자 컨텍스트 활용
            if user_context:
                areas = user_context.get("areas", [])
                interests = user_context.get("interests", [])

                # 텍스트에 포함된 area/interest 찾기
                for item in areas + interests:
                    if item and str(item) in text:
                        found_tags.append(str(item))

            # 2. 기본 키워드 매칭
            keyword_dict = {
                "개발": ["개발", "코드", "프로그래밍", "api", "버그", "디버깅"],
                "디자인": ["디자인", "ui", "ux", "figma", "색상", "레이아웃"],
                "회의": ["회의", "미팅", "논의", "결정", "안건"],
                "기획": ["기획", "전략", "계획", "목표", "방향성"],
                "마케팅": ["마케팅", "광고", "홍보", "캠페인", "고객"],
                "데이터": ["데이터", "분석", "통계", "차트", "지표"],
            }

            normalized_text = text.lower()
            for category, keywords in keyword_dict.items():
                if any(kw in normalized_text for kw in keywords):
                    found_tags.append(category)

            # 중복 제거
            found_tags = list(set(found_tags))

            return found_tags if found_tags else ["기타"]

        except Exception as e:
            logger.warning(f"[{self.instance_id}] ⚠️ 태그 강제 추출 실패: {e}")
            return ["기타"]

    def _create_empty_response(self) -> Dict[str, Any]:
        """빈 응답"""
        return {
            "tags": ["기타"],
            "confidence": 0.0,
            "matched_keywords": {},
            "reasoning": "명확한 키워드 없음",
            "para_hints": {},
            "user_context_matched": False,
            "user_areas": [],
            "instance_id": self.instance_id,
            "processing_time": "0.0s",
            "error": "empty_input",
        }

    def get_statistics(self) -> Dict[str, Any]:
        """분류기 통계"""
        return {
            "instance_id": self.instance_id,
            "created_at": self.created_at,
            "llm_initialized": self.llm is not None,
            "chain_initialized": self.chain is not None,
            "model": ModelConfig.GPT4O_MINI_MODEL if self.llm else "None",
            "api_configured": bool(ModelConfig.GPT4O_MINI_API_KEY),
        }


# ============================================================
# 테스트 메인 함수
# ============================================================

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    print("\n" + "=" * 70)
    print("KeywordClassifier 테스트 (프롬프트 파일 그대로 사용!)")
    print("=" * 70)

    # 동기 테스트
    classifier1 = KeywordClassifier()

    test_texts = [
        "오늘 회의가 있고, 저녁에 스터디 모임이 있습니다.",
        "일기를 쓰면서 오늘 하루를 돌아봅니다.",
        "오늘 헬스장에 가서 운동했습니다.",
    ]

    user_context = {
        "occupation": "소프트웨어 엔지니어",
        "areas": ["코드 품질 관리", "기술 역량 개발"],
        "interests": ["AI", "백엔드 개발"],
    }

    print("\n" + "=" * 70)
    print("동기 테스트 (사용자 컨텍스트 포함)")
    print("=" * 70)

    for i, text in enumerate(test_texts, 1):
        print(f"\n📝 테스트 {i}: {text}")
        result = classifier1.classify(text, user_context=user_context)
        print(f"✅ 태그: {result['tags']}")
        print(f"📊 신뢰도: {result['confidence']}")
        print(f"🆔 Instance: {result.get('instance_id')}")
        print(f"👤 User matched: {result.get('user_context_matched')}")

    # 비동기 테스트
    print("\n" + "=" * 70)
    print("비동기 테스트")
    print("=" * 70)

    async def async_test():
        classifier2 = KeywordClassifier()  # 새 인스턴스!

        for i, text in enumerate(test_texts, 1):
            print(f"\n📝 비동기 테스트 {i}: {text}")
            result = await classifier2.aclassify(text, user_context=user_context)
            print(f"✅ 태그: {result['tags']}")
            print(f"📊 신뢰도: {result['confidence']}")
            print(f"🆔 Instance: {result.get('instance_id')}")
            print(f"⏱️  Time: {result.get('processing_time')}")
            print(f"👤 User areas: {result.get('user_areas')}")

    asyncio.run(async_test())

##############################################################################


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


"""test_result_6 → ⭕️ 

    python -m backend.classifier.keyword_classifier

    ======================================================================
    KeywordClassifier 테스트 (프롬프트 파일 그대로 사용!)
    ======================================================================
    2025-11-09 23:30:54,219 - INFO - ✅ KeywordClassifier LLM 초기화 성공
    2025-11-09 23:30:54,221 - INFO - [3587ef52] ✅ Chain 생성 성공 (프롬프트 파일 로드 완료)
    2025-11-09 23:30:54,221 - INFO - ✅ KeywordClassifier initialized (ID: 3587ef52, Time: 23:30:54)

    ======================================================================
    동기 테스트 (사용자 컨텍스트 포함)
    ======================================================================

    📝 테스트 1: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다.
    2025-11-09 23:30:54,221 - INFO - 🔍 [3587ef52] CLASSIFY 시작: text_len=28, has_context=True
    2025-11-09 23:30:54,221 - INFO - [3587ef52] 🔍 Calling LLM (sync)...
    2025-11-09 23:30:58,985 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-09 23:30:59,003 - INFO - [3587ef52] ✅ 분류 완료 (sync):
    2025-11-09 23:30:59,003 - INFO - [3587ef52]   - Tags: ['코드', '품질', '개선', '테스트']
    ✅ 태그: ['코드', '품질', '개선', '테스트']
    📊 신뢰도: 0.85
    🆔 Instance: 3587ef52
    👤 User matched: True

    📝 테스트 2: 일기를 쓰면서 오늘 하루를 돌아봅니다.
    2025-11-09 23:30:59,003 - INFO - 🔍 [3587ef52] CLASSIFY 시작: text_len=21, has_context=True
    2025-11-09 23:30:59,004 - INFO - [3587ef52] 🔍 Calling LLM (sync)...
    2025-11-09 23:31:03,820 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-09 23:31:03,823 - INFO - [3587ef52] ✅ 분류 완료 (sync):
    2025-11-09 23:31:03,823 - INFO - [3587ef52]   - Tags: ['코드', '품질', '관리', '테스트', '리팩토링']
    ✅ 태그: ['코드', '품질', '관리', '테스트', '리팩토링']
    📊 신뢰도: 0.9
    🆔 Instance: 3587ef52
    👤 User matched: True

    📝 테스트 3: 오늘 헬스장에 가서 운동했습니다.
    2025-11-09 23:31:03,823 - INFO - 🔍 [3587ef52] CLASSIFY 시작: text_len=18, has_context=True
    2025-11-09 23:31:03,823 - INFO - [3587ef52] 🔍 Calling LLM (sync)...
    2025-11-09 23:31:09,864 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-09 23:31:09,867 - INFO - [3587ef52] ✅ 분류 완료 (sync):
    2025-11-09 23:31:09,867 - INFO - [3587ef52]   - Tags: ['코드', '품질', '관리', '테스트', '리팩토링']
    ✅ 태그: ['코드', '품질', '관리', '테스트', '리팩토링']
    📊 신뢰도: 0.85
    🆔 Instance: 3587ef52
    👤 User matched: True

    ======================================================================
    비동기 테스트
    ======================================================================
    2025-11-09 23:31:09,868 - INFO - ✅ KeywordClassifier LLM 초기화 성공
    2025-11-09 23:31:09,871 - INFO - [fdc6dd02] ✅ Chain 생성 성공 (프롬프트 파일 로드 완료)
    2025-11-09 23:31:09,871 - INFO - ✅ KeywordClassifier initialized (ID: fdc6dd02, Time: 23:31:09)

    📝 비동기 테스트 1: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다.
    2025-11-09 23:31:09,871 - INFO - [fdc6dd02] 🔍 Calling LLM (async)...
    2025-11-09 23:31:09,871 - INFO - [fdc6dd02]   - Text length: 28
    2025-11-09 23:31:09,871 - INFO - [fdc6dd02]   - Occupation: 소프트웨어 엔지니어
    2025-11-09 23:31:09,872 - INFO - [fdc6dd02]   - Areas: 코드 품질 관리, 기술 역량 개발
    2025-11-09 23:31:13,576 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-09 23:31:13,579 - INFO - [fdc6dd02] ✅ 분류 완료 (async):
    2025-11-09 23:31:13,579 - INFO - [fdc6dd02]   - Tags: ['웹앱', '개발', '팀', '환경 구축', '12/31']
    2025-11-09 23:31:13,579 - INFO - [fdc6dd02]   - Confidence: 0.95
    2025-11-09 23:31:13,579 - INFO - [fdc6dd02]   - Time: 3.71s
    ✅ 태그: ['웹앱', '개발', '팀', '환경 구축', '12/31']
    📊 신뢰도: 0.95
    🆔 Instance: fdc6dd02
    ⏱️  Time: 3.71s
    👤 User areas: ['코드 품질 관리', '기술 역량 개발']

    📝 비동기 테스트 2: 일기를 쓰면서 오늘 하루를 돌아봅니다.
    2025-11-09 23:31:13,579 - INFO - [fdc6dd02] 🔍 Calling LLM (async)...
    2025-11-09 23:31:13,579 - INFO - [fdc6dd02]   - Text length: 21
    2025-11-09 23:31:13,579 - INFO - [fdc6dd02]   - Occupation: 소프트웨어 엔지니어
    2025-11-09 23:31:13,579 - INFO - [fdc6dd02]   - Areas: 코드 품질 관리, 기술 역량 개발
    2025-11-09 23:31:17,959 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-09 23:31:17,964 - INFO - [fdc6dd02] ✅ 분류 완료 (async):
    2025-11-09 23:31:17,964 - INFO - [fdc6dd02]   - Tags: ['코드', '품질', '관리', '테스트', '리팩토링']
    2025-11-09 23:31:17,964 - INFO - [fdc6dd02]   - Confidence: 0.88
    2025-11-09 23:31:17,964 - INFO - [fdc6dd02]   - Time: 4.38s
    ✅ 태그: ['코드', '품질', '관리', '테스트', '리팩토링']
    📊 신뢰도: 0.88
    🆔 Instance: fdc6dd02
    ⏱️  Time: 4.38s
    👤 User areas: ['코드 품질 관리', '기술 역량 개발']

    📝 비동기 테스트 3: 오늘 헬스장에 가서 운동했습니다.
    2025-11-09 23:31:17,964 - INFO - [fdc6dd02] 🔍 Calling LLM (async)...
    2025-11-09 23:31:17,964 - INFO - [fdc6dd02]   - Text length: 18
    2025-11-09 23:31:17,964 - INFO - [fdc6dd02]   - Occupation: 소프트웨어 엔지니어
    2025-11-09 23:31:17,964 - INFO - [fdc6dd02]   - Areas: 코드 품질 관리, 기술 역량 개발
    2025-11-09 23:31:27,785 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-09 23:31:27,789 - INFO - [fdc6dd02] ✅ 분류 완료 (async):
    2025-11-09 23:31:27,789 - INFO - [fdc6dd02]   - Tags: ['코드 품질 관리', '테스트', '리팩토링', '버그', '품질']
    2025-11-09 23:31:27,789 - INFO - [fdc6dd02]   - Confidence: 0.85
    2025-11-09 23:31:27,790 - INFO - [fdc6dd02]   - Time: 9.83s
    ✅ 태그: ['코드 품질 관리', '테스트', '리팩토링', '버그', '품질']
    📊 신뢰도: 0.85
    🆔 Instance: fdc6dd02
    ⏱️  Time: 9.83s
    👤 User areas: ['코드 품질 관리', '기술 역량 개발']

"""


"""test_result_7 → ⭕️ 

    python -m backend.classifier.keyword_classifier

    ======================================================================
    KeywordClassifier 테스트 (프롬프트 파일 그대로 사용!)
    ======================================================================
    2025-11-10 23:04:45,242 - INFO - ✅ KeywordClassifier LLM 초기화 성공
    2025-11-10 23:04:45,243 - INFO - [f63cf9b2] ✅ Chain 생성 성공 (프롬프트 파일 로드 완료)
    2025-11-10 23:04:45,243 - INFO - ✅ KeywordClassifier initialized (ID: f63cf9b2, Time: 23:04:45)

    ======================================================================
    동기 테스트 (사용자 컨텍스트 포함)
    ======================================================================

    📝 테스트 1: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다.
    2025-11-10 23:04:45,243 - INFO - 🔍 [f63cf9b2] CLASSIFY 시작: text_len=28, has_context=True
    2025-11-10 23:04:45,243 - INFO - [f63cf9b2] 🔍 Calling LLM (sync)...
    2025-11-10 23:04:52,809 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-10 23:04:52,821 - INFO - [f63cf9b2] ✅ 분류 완료 (sync):
    2025-11-10 23:04:52,822 - INFO - [f63cf9b2]   - Tags: ['코드', '품질', '관리', '테스트', '리팩토링']
    ✅ 태그: ['코드', '품질', '관리', '테스트', '리팩토링']
    📊 신뢰도: 0.9
    🆔 Instance: f63cf9b2
    👤 User matched: True

    📝 테스트 2: 일기를 쓰면서 오늘 하루를 돌아봅니다.
    2025-11-10 23:04:52,822 - INFO - 🔍 [f63cf9b2] CLASSIFY 시작: text_len=21, has_context=True
    2025-11-10 23:04:52,822 - INFO - [f63cf9b2] 🔍 Calling LLM (sync)...
    2025-11-10 23:05:00,044 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-10 23:05:00,046 - INFO - [f63cf9b2] ✅ 분류 완료 (sync):
    2025-11-10 23:05:00,046 - INFO - [f63cf9b2]   - Tags: ['코드', '품질', '관리', '테스트', '리팩토링']
    ✅ 태그: ['코드', '품질', '관리', '테스트', '리팩토링']
    📊 신뢰도: 0.85
    🆔 Instance: f63cf9b2
    👤 User matched: True

    📝 테스트 3: 오늘 헬스장에 가서 운동했습니다.
    2025-11-10 23:05:00,046 - INFO - 🔍 [f63cf9b2] CLASSIFY 시작: text_len=18, has_context=True
    2025-11-10 23:05:00,046 - INFO - [f63cf9b2] 🔍 Calling LLM (sync)...
    2025-11-10 23:05:05,814 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-10 23:05:05,816 - INFO - [f63cf9b2] ✅ 분류 완료 (sync):
    2025-11-10 23:05:05,816 - INFO - [f63cf9b2]   - Tags: ['코드', '품질', '관리', '개발', '테스트']
    ✅ 태그: ['코드', '품질', '관리', '개발', '테스트']
    📊 신뢰도: 0.9
    🆔 Instance: f63cf9b2
    👤 User matched: True

    ======================================================================
    비동기 테스트
    ======================================================================
    2025-11-10 23:05:05,817 - INFO - ✅ KeywordClassifier LLM 초기화 성공
    2025-11-10 23:05:05,819 - INFO - [24f8e519] ✅ Chain 생성 성공 (프롬프트 파일 로드 완료)
    2025-11-10 23:05:05,819 - INFO - ✅ KeywordClassifier initialized (ID: 24f8e519, Time: 23:05:05)

    📝 비동기 테스트 1: 오늘 회의가 있고, 저녁에 스터디 모임이 있습니다.
    2025-11-10 23:05:05,819 - INFO - [24f8e519] 🔍 Calling LLM (async)...
    2025-11-10 23:05:05,819 - INFO - [24f8e519]   - Text length: 28
    2025-11-10 23:05:05,819 - INFO - [24f8e519]   - Occupation: 소프트웨어 엔지니어
    2025-11-10 23:05:05,819 - INFO - [24f8e519]   - Areas: 코드 품질 관리, 기술 역량 개발
    2025-11-10 23:05:05,819 - INFO - [24f8e519]   - Context Keywords: {}
    2025-11-10 23:05:19,640 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-10 23:05:19,647 - INFO - [24f8e519] 📦 RAW LLM Response:
    2025-11-10 23:05:19,647 - INFO - [24f8e519]   - Type: <class 'str'>
    2025-11-10 23:05:19,647 - INFO - [24f8e519]   - Content preview: ```json
    {
    "tags": ["코드", "품질", "리뷰", "버그", "개발"],
    "confidence": 0.85,
    "matched_keywords": {
        "Projects": ["마감", "팀"],
        "Areas": ["품질", "관리"],
        "Resources": [],
        "Archives": []
    },
    
    2025-11-10 23:05:19,647 - INFO - [24f8e519] 📦 Extracted tags: ['코드', '품질', '리뷰', '버그', '개발'] (type: <class 'list'>)
    2025-11-10 23:05:19,647 - INFO - [24f8e519] ✅ 리스트 검증 완료: 5개
    2025-11-10 23:05:19,647 - INFO - [24f8e519] 📦 Extracted tags: ['코드', '품질', '리뷰', '버그', '개발'] (type: <class 'list'>)
    2025-11-10 23:05:19,647 - INFO - [24f8e519] ✅ 리스트 검증 완료: 5개
    2025-11-10 23:05:19,647 - INFO - [24f8e519] ✅ 분류 완료 (async):
    2025-11-10 23:05:19,647 - INFO - [24f8e519]   - Tags: ['코드', '품질', '리뷰', '버그', '개발']
    2025-11-10 23:05:19,647 - INFO - [24f8e519]   - Confidence: 0.85
    2025-11-10 23:05:19,647 - INFO - [24f8e519]   - Time: 13.83s
    ✅ 태그: ['코드', '품질', '리뷰', '버그', '개발']
    📊 신뢰도: 0.85
    🆔 Instance: 24f8e519
    ⏱️  Time: 13.83s
    👤 User areas: ['코드 품질 관리', '기술 역량 개발']

    📝 비동기 테스트 2: 일기를 쓰면서 오늘 하루를 돌아봅니다.
    2025-11-10 23:05:19,647 - INFO - [24f8e519] 🔍 Calling LLM (async)...
    2025-11-10 23:05:19,648 - INFO - [24f8e519]   - Text length: 21
    2025-11-10 23:05:19,648 - INFO - [24f8e519]   - Occupation: 소프트웨어 엔지니어
    2025-11-10 23:05:19,648 - INFO - [24f8e519]   - Areas: 코드 품질 관리, 기술 역량 개발
    2025-11-10 23:05:19,648 - INFO - [24f8e519]   - Context Keywords: {}
    2025-11-10 23:05:25,578 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-10 23:05:25,581 - INFO - [24f8e519] 📦 RAW LLM Response:
    2025-11-10 23:05:25,581 - INFO - [24f8e519]   - Type: <class 'str'>
    2025-11-10 23:05:25,581 - INFO - [24f8e519]   - Content preview: ```json
    {
    "tags": ["코드", "품질", "리뷰", "개발", "테스트"],
    "confidence": 0.85,
    "matched_keywords": {
        "Projects": [],
        "Areas": ["코드", "품질", "리뷰", "테스트"],
        "Resources": [],
        "Archives": []
    
    2025-11-10 23:05:25,581 - INFO - [24f8e519] 📦 Extracted tags: ['코드', '품질', '리뷰', '개발', '테스트'] (type: <class 'list'>)
    2025-11-10 23:05:25,581 - INFO - [24f8e519] ✅ 리스트 검증 완료: 5개
    2025-11-10 23:05:25,581 - INFO - [24f8e519] 📦 Extracted tags: ['코드', '품질', '리뷰', '개발', '테스트'] (type: <class 'list'>)
    2025-11-10 23:05:25,581 - INFO - [24f8e519] ✅ 리스트 검증 완료: 5개
    2025-11-10 23:05:25,581 - INFO - [24f8e519] ✅ 분류 완료 (async):
    2025-11-10 23:05:25,581 - INFO - [24f8e519]   - Tags: ['코드', '품질', '리뷰', '개발', '테스트']
    2025-11-10 23:05:25,581 - INFO - [24f8e519]   - Confidence: 0.85
    2025-11-10 23:05:25,581 - INFO - [24f8e519]   - Time: 5.93s
    ✅ 태그: ['코드', '품질', '리뷰', '개발', '테스트']
    📊 신뢰도: 0.85
    🆔 Instance: 24f8e519
    ⏱️  Time: 5.93s
    👤 User areas: ['코드 품질 관리', '기술 역량 개발']

    📝 비동기 테스트 3: 오늘 헬스장에 가서 운동했습니다.
    2025-11-10 23:05:25,581 - INFO - [24f8e519] 🔍 Calling LLM (async)...
    2025-11-10 23:05:25,581 - INFO - [24f8e519]   - Text length: 18
    2025-11-10 23:05:25,581 - INFO - [24f8e519]   - Occupation: 소프트웨어 엔지니어
    2025-11-10 23:05:25,581 - INFO - [24f8e519]   - Areas: 코드 품질 관리, 기술 역량 개발
    2025-11-10 23:05:25,582 - INFO - [24f8e519]   - Context Keywords: {}
    2025-11-10 23:05:31,824 - INFO - HTTP Request: POST https://**** "HTTP/1.1 200 OK"
    2025-11-10 23:05:31,827 - INFO - [24f8e519] 📦 RAW LLM Response:
    2025-11-10 23:05:31,827 - INFO - [24f8e519]   - Type: <class 'str'>
    2025-11-10 23:05:31,827 - INFO - [24f8e519]   - Content preview: ```json
    {
    "tags": ["코드", "품질", "리뷰", "테스트", "리팩토링"],
    "confidence": 0.85,
    "matched_keywords": {
        "Projects": [],
        "Areas": ["코드", "품질", "리뷰"],
        "Resources": [],
        "Archives": []
    },
    
    2025-11-10 23:05:31,827 - INFO - [24f8e519] 📦 Extracted tags: ['코드', '품질', '리뷰', '테스트', '리팩토링'] (type: <class 'list'>)
    2025-11-10 23:05:31,827 - INFO - [24f8e519] ✅ 리스트 검증 완료: 5개
    2025-11-10 23:05:31,827 - INFO - [24f8e519] 📦 Extracted tags: ['코드', '품질', '리뷰', '테스트', '리팩토링'] (type: <class 'list'>)
    2025-11-10 23:05:31,827 - INFO - [24f8e519] ✅ 리스트 검증 완료: 5개
    2025-11-10 23:05:31,827 - INFO - [24f8e519] ✅ 분류 완료 (async):
    2025-11-10 23:05:31,827 - INFO - [24f8e519]   - Tags: ['코드', '품질', '리뷰', '테스트', '리팩토링']
    2025-11-10 23:05:31,828 - INFO - [24f8e519]   - Confidence: 0.85
    2025-11-10 23:05:31,828 - INFO - [24f8e519]   - Time: 6.25s
    ✅ 태그: ['코드', '품질', '리뷰', '테스트', '리팩토링']
    📊 신뢰도: 0.85
    🆔 Instance: 24f8e519
    ⏱️  Time: 6.25s
    👤 User areas: ['코드 품질 관리', '기술 역량 개발']

"""

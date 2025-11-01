# backend/classifier/langchain_integration.py

"""
LangChain을 사용한 PARA 분류 통합 모듈 (메타데이터 대비)
GPT-4o-mini를 사용한 AI 기반 분류
- 상대경로 + 동적 버전
- 정규표현식 사용
"""

import json
import logging
import os
import sys
import re
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv

# 상대경로 + 동적 계산
CURRENT_FILE = Path(__file__)
CLASSIFIER_DIR = CURRENT_FILE.parent
BACKEND_DIR = CLASSIFIER_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# 1. .env 파일 로드
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(str(ENV_FILE))

# 2. sys.path에 경로 추가
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

# 3. config import (3단계 fallback)
try:
    # 1번째 시도: 절대 import
    from backend.config import ModelConfig
    print("✅ ModelConfig loaded from backend.config")
except ImportError:
    try:
        # 2번째 시도: 상대 import
        from config import ModelConfig
        print("✅ ModelConfig loaded from config")
    except ImportError:
        # 3번째 시도: 직접 환경변수
        print("⚠️ Using os.getenv fallback")
        class ModelConfig:
            GPT4O_MINI_API_KEY = os.getenv("GPT4O_MINI_API_KEY")
            GPT4O_MINI_BASE_URL = os.getenv("GPT4O_MINI_BASE_URL")
            GPT4O_MINI_MODEL = os.getenv("GPT4O_MINI_MODEL", "gpt-4o-mini")


logger = logging.getLogger(__name__)


class PARAClassificationOutput(BaseModel):
    """PARA 분류 결과 스키마"""
    category: str = Field(description="PARA 카테고리 (Projects/Areas/Resources/Archives)")
    confidence: float = Field(description="신뢰도 점수 (0.0-1.0)")
    reasoning: str = Field(description="분류 이유 (한국어)")
    detected_cues: List[str] = Field(description="감지된 키워드 목록")


def escape_json_braces_complete(content: str) -> str:
    """모든 JSON 형식의 중괄호를 이스케이프"""
    
    # 1. 백틱(```
    # ```
    # {
    #   "key": "value"
    # }
    # ```
    
    # 패턴: ```로 시작하고 ```
    def escape_code_block(match):
        code_block = match.group(0)
        # 코드 블록 내의 { → {{ 치환
        code_block = code_block.replace('{\n', '{{\n')
        code_block = code_block.replace('\n}', '\n}}')
        code_block = code_block.replace('{ ', '{{ ')
        code_block = code_block.replace(' }', ' }}')
        return code_block
    
    # ```...```
    content = re.sub(r'``````', escape_code_block, content)
    
    # 2. 일반 { } 처리 (백틱 밖)
    # {{ → {{{ 로 안 되게 조심하기
    lines = []
    in_code = False
    
    for line in content.split('\n'):
        if line.strip().startswith('```'):
            in_code = not in_code
            lines.append(line)
        elif not in_code and re.match(r'^\s*\{', line):
            # 라인이 { 로 시작
            line = re.sub(r'\{\s', '{{ ', line)
            line = re.sub(r'\{$', '{{', line)
            lines.append(line)
        elif not in_code and re.search(r'\}\s*$', line):
            # 라인이 } 로 끝남
            line = re.sub(r'\s\}', ' }}', line)
            line = re.sub(r'^}', '}}', line)
            lines.append(line)
        else:
            lines.append(line)
    
    return '\n'.join(lines)


def get_para_classification_prompt() -> str:
    """프롬프트 파일 읽기 + 간단한 이스케이프"""
    
    prompt_path = CLASSIFIER_DIR / "prompts" / "para_classification_prompt.txt"
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # ✅ 간단한 이스케이프
    lines = []
    for line in content.split('\n'):
        # {text}는 건드리지 말고
        if '{text}' in line:
            lines.append(line)
        else:
            # 나머지 { } 는 이스케이프
            line = line.replace('{', '{{').replace('}', '}}')
            # {text}는 원상복구
            line = line.replace('{{text}}', '{text}')
            lines.append(line)
    
    return '\n'.join(lines)


def create_para_prompt(include_metadata: bool = False) -> PromptTemplate:
    """메타데이터 옵션이 있는 프롬프트 생성
    
    Args:
        include_metadata: 메타데이터 포함 여부
    
    Returns:
        PromptTemplate: LangChain 프롬프트
    """
    
    # 기본 프롬프트 로드
    base_prompt = get_para_classification_prompt()
    
    if include_metadata:
        # 메타데이터 섹션 추가
        metadata_instruction = """
## 📋 추가 파일 정보
- 파일명: {filename}
- 생성일: {created_date}
- 태그: {tags}

💡 팁: 메타데이터도 고려하되, 본문 내용이 명확하면 본문을 우선하세요.
"""
        full_prompt = base_prompt + metadata_instruction
        input_variables = ["text", "filename", "created_date", "tags"]
    else:
        full_prompt = base_prompt
        input_variables = ["text"]
    
    # 프롬프트 생성
    prompt = PromptTemplate(
        input_variables=input_variables,
        template=full_prompt
    )
    
    return prompt


def create_para_chain(include_metadata: bool = False):
    """
    PARA 분류를 위한 LangChain Chain 생성
    
    Args:
        include_metadata: 메타데이터 포함 여부
    
    Returns:
        Runnable: LangChain 실행 가능 객체
    """
    
    # ✅ config의 설정으로 LLM 초기화
    llm = ChatOpenAI(
        api_key=ModelConfig.GPT4O_MINI_API_KEY,
        base_url=ModelConfig.GPT4O_MINI_BASE_URL,
        model=ModelConfig.GPT4O_MINI_MODEL,
        temperature=0.3,
        max_tokens=500
    )
    
    # 프롬프트 생성
    prompt = create_para_prompt(include_metadata=include_metadata)
    
    # JSON 출력 파서
    parser = JsonOutputParser(pydantic_object=PARAClassificationOutput)
    
    # Chain 구성: Prompt → LLM → Parser
    chain = prompt | llm | parser
    
    return chain


def classify_with_langchain(
    text: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    LangChain을 사용해 텍스트를 PARA로 분류
    메타데이터 옵션으로 미래 확장 대비
    
    Args:
        text (str): 분류할 텍스트
        metadata (Optional[Dict]): 옵션 메타데이터
            {
                "filename": str,
                "created_date": str,
                "tags": List[str]
            }
    
    Returns:
        Dict: 분류 결과
            {
                "category": str,
                "confidence": float,
                "reasoning": str,
                "detected_cues": List[str],
                "source": str,
                "has_metadata": bool
            }
    """
    
    try:
        # 메타데이터 포함 여부 결정
        include_metadata = metadata is not None
        
        # Chain 생성
        chain = create_para_chain(include_metadata=include_metadata)
        
        # 입력 데이터 구성
        input_data = {"text": text}
        
        if include_metadata:
            input_data.update({
                "filename": metadata.get("filename", "N/A"),
                "created_date": metadata.get("created_date", "N/A"),
                "tags": ", ".join(metadata.get("tags", [])) or "None"
            })
        
        # 분류 실행
        result = chain.invoke(input_data)
        
        logger.info(
            f"분류 완료: {result['category']} "
            f"(confidence: {result['confidence']:.2%}, "
            f"metadata: {include_metadata})"
        )
        
        return {
            "category": result["category"],
            "confidence": result["confidence"],
            "reasoning": result["reasoning"],
            "detected_cues": result.get("detected_cues", []),
            "source": "langchain",
            "has_metadata": include_metadata
        }
    
    except Exception as e:
        logger.error(f"LangChain 분류 중 오류: {str(e)}")
        raise


# 테스트용
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Config 기반 LangChain 테스트")
    print("=" * 60)
    print(f"API Key: {ModelConfig.GPT4O_MINI_API_KEY[:3]}..." if ModelConfig.GPT4O_MINI_API_KEY else "❌ API Key 없음")
    print(f"API Base: {ModelConfig.GPT4O_MINI_BASE_URL[:3]}..................." if ModelConfig.GPT4O_MINI_BASE_URL else "❌ API Base 못찾음")
    print(f"Model: {ModelConfig.GPT4O_MINI_MODEL}" if ModelConfig.GPT4O_MINI_MODEL else "❌ Model 없음")
    print("=" * 60)


    # 테스트 1: 텍스트만
    test_text_1 = "11월 30일까지 완성해야 하는 프로젝트 제안서"
    
    print("=" * 60)
    print("테스트 1: 텍스트만 분류")
    print("=" * 60)
    
    try:
        result = classify_with_langchain(test_text_1)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"오류: {e}")
    
    # 테스트 2: 메타데이터 포함
    print("\n테스트 2: 메타데이터 포함 분류\n")
    test_text_2 = "마케팅 전략"
    test_metadata = {
        "filename": "marketing_strategy_2025.md",
        "created_date": "2025-01-01",
        "tags": ["work", "important"]
    }
    
    print("\n" + "=" * 60)
    print("테스트 2: 메타데이터 포함 분류")
    print("=" * 60)
    
    try:
        result = classify_with_langchain(test_text_2, metadata=test_metadata)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"오류: {e}")



"""test_result

    ✅ ModelConfig loaded from backend.config
    ============================================================
    Config 기반 LangChain 테스트
    ============================================================
    API Key: eyJ...
    API Base: htt...................
    Model: openai/gpt-4o-mini
    ============================================================
    ============================================================
    테스트 1: 텍스트만 분류
    ============================================================
    INFO:http****** "HTTP/1.1 200 OK"
    INFO:__main__:분류 완료: Projects (confidence: 100.00%, metadata: False)
        {
        "category": "Projects",
        "confidence": 1.0,
        "reasoning": "기한(11월 30일까지)과 구체적 목표(완성해야 하는 프로젝트 제안서)가 명시되어 있어 Projects로 분류됨.",
        "detected_cues": [
            "11월 30일까지",
            "완성해야 하는",
            "프로젝트 제안서"
        ],
        "source": "langchain",
        "has_metadata": false
        }

    ============================================================
    테스트 2: 메타데이터 포함 분류
    ============================================================
    INFO:http****** "HTTP/1.1 200 OK"
    INFO:__main__:분류 완료: Areas (confidence: 80.00%, metadata: True)
    {
    "category": "Areas",
    "confidence": 0.8,
    "reasoning": "지속적인 관심 영역인 '마케팅 전략'으로, 구체적인 기한이나 완료 표현이 없어 Areas로 분류됨.",
    "detected_cues": [],
    "source": "langchain",
    "has_metadata": true
    }

"""
# backend/classifier/langchain_integration.py

"""
LangChain-based PARA classification integration module.
Uses GPT-4o-mini for AI-powered document classification.
- Dynamic path resolution (no hardcoded paths)
- Regex-based brace escaping for PromptTemplate compatibility
- Supports text-only, metadata-only, and hybrid classification modes
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import openai
from dotenv import load_dotenv
from langchain_core.exceptions import OutputParserException

from backend.agent.error_utils import build_meta, log_agent_error

# Resolve paths dynamically to avoid hardcoding
CURRENT_FILE = Path(__file__)
CLASSIFIER_DIR = CURRENT_FILE.parent
BACKEND_DIR = CLASSIFIER_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Load environment variables from project root .env
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(str(ENV_FILE))

# Ensure backend and project root are importable
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

# Unified model migration import
from backend.models import PARAClassificationOutput

# 3-level fallback for ModelConfig to support both package and standalone execution
try:
    # Attempt 1: absolute import (standard app context)
    from backend.config import ModelConfig

    print("ModelConfig loaded from backend.config")
except ImportError:
    try:
        # Attempt 2: relative import (when run from within backend/)
        from config import ModelConfig

        print("ModelConfig loaded from config")
    except ImportError:
        # Attempt 3: fallback to raw environment variables
        print("[WARN] Using os.getenv fallback for ModelConfig")

        class ModelConfig:
            GPT4O_MINI_API_KEY = os.getenv("GPT4O_MINI_API_KEY")
            GPT4O_MINI_BASE_URL = os.getenv("GPT4O_MINI_BASE_URL")
            GPT4O_MINI_MODEL = os.getenv("GPT4O_MINI_MODEL", "gpt-4o-mini")


logger = logging.getLogger(__name__)


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
        code_block = code_block.replace("{\n", "{{\n")
        code_block = code_block.replace("\n}", "\n}}")
        code_block = code_block.replace("{ ", "{{ ")
        code_block = code_block.replace(" }", " }}")
        return code_block

    # ```...```
    content = re.sub(r"``````", escape_code_block, content)

    # 2. 일반 { } 처리 (백틱 밖)
    # {{ → {{{ 로 안 되게 조심하기
    lines = []
    in_code = False

    for line in content.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            lines.append(line)
        elif not in_code and re.match(r"^\s*\{", line):
            # 라인이 { 로 시작
            line = re.sub(r"\{\s", "{{ ", line)
            line = re.sub(r"\{$", "{{", line)
            lines.append(line)
        elif not in_code and re.search(r"\}\s*$", line):
            # 라인이 } 로 끝남
            line = re.sub(r"\s\}", " }}", line)
            line = re.sub(r"^}", "}}", line)
            lines.append(line)
        else:
            lines.append(line)

    return "\n".join(lines)


def get_para_classification_prompt() -> str:
    """Read the PARA classification prompt file and escape braces for PromptTemplate."""

    prompt_path = CLASSIFIER_DIR / "prompts" / "para_classification_prompt.txt"

    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Escape all curly braces so PromptTemplate doesn't misinterpret them
    lines = []
    for line in content.split("\n"):
        if "{text}" not in line:
            # Escape all other braces for PromptTemplate compatibility
            line = line.replace("{", "{{").replace("}", "}}")
            # Restore {text} after the blanket escape
            line = line.replace("{{text}}", "{text}")
        # Leave lines that contain the template variable {text} untouched
        lines.append(line)

    return "\n".join(lines)


def create_para_prompt(include_metadata: bool = False) -> PromptTemplate:
    """메타데이터 옵션이 있는 프롬프트 생성

    Args:
        include_metadata: 메타데이터 포함 여부

    Returns:
        PromptTemplate: LangChain 프롬프트
    """

    # Load the base PARA classification prompt from disk
    base_prompt = get_para_classification_prompt()

    if include_metadata:
        # Append metadata section when additional file context is available
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

    # Build and return the LangChain PromptTemplate
    return PromptTemplate(input_variables=input_variables, template=full_prompt)


def create_para_chain(include_metadata: bool = False):
    """
    PARA 분류를 위한 LangChain Chain 생성

    Args:
        include_metadata: 메타데이터 포함 여부

    Returns:
        Runnable: LangChain 실행 가능 객체
    """

    # Initialize LLM using config-driven settings (no hardcoded keys or URLs)
    llm = ChatOpenAI(
        api_key=ModelConfig.GPT4O_MINI_API_KEY,
        base_url=ModelConfig.GPT4O_MINI_BASE_URL,
        model=ModelConfig.GPT4O_MINI_MODEL,
        temperature=0.3,
        max_tokens=500,
    )

    # Build the prompt template with or without metadata fields
    prompt = create_para_prompt(include_metadata=include_metadata)

    # JSON output parser bound to the PARAClassificationOutput Pydantic schema
    parser = JsonOutputParser(pydantic_object=PARAClassificationOutput)

    # Compose the LCEL chain: Prompt -> LLM -> Parser
    return prompt | llm | parser


def _build_langchain_input(
    text: str, metadata: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Assemble the chain input dict, merging metadata fields when present."""
    if metadata is not None:
        return {
            "text": text,
            "filename": metadata.get("filename", "N/A"),
            "created_date": metadata.get("created_date", "N/A"),
            "tags": ", ".join(metadata.get("tags", [])) or "None",
        }
    return {"text": text}


def _merge_confidence_weighted(
    text_result: Dict[str, Any], metadata_result: Dict[str, Any]
) -> tuple[str, float, str]:
    """Apply confidence-weighted merge strategy and return (category, confidence, strategy)."""
    text_conf = text_result["confidence"]
    meta_conf = metadata_result["confidence"]

    if text_conf >= 0.7:
        # Text-dominant when confidence >= 70% (weight: text 70% + metadata 30%)
        return (
            text_result["category"],
            min(text_conf * 0.7 + meta_conf * 0.3, 1.0),
            "text_dominant (0.7:0.3)",
        )
    if text_conf >= 0.5:
        # Balanced merge when text confidence falls between 50-70%
        if text_result["category"] == metadata_result["category"]:
            # Agreement boosts confidence
            return (
                text_result["category"],
                max(text_conf, meta_conf),
                "balanced (0.5:0.5)",
            )
        # On conflict, prefer metadata as it carries more explicit signals
        return (
            metadata_result["category"],
            min(text_conf * 0.5 + meta_conf * 0.5, 1.0),
            "balanced (0.5:0.5)",
        )
    # Metadata-dominant when text confidence < 50% (weight: text 30% + metadata 70%)
    return (
        metadata_result["category"],
        min(text_conf * 0.3 + meta_conf * 0.7, 1.0),
        "metadata_dominant (0.3:0.7)",
    )


def classify_with_langchain(
    text: str, metadata: Optional[Dict[str, Any]] = None
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
        # Determine whether to include optional metadata in the prompt
        include_metadata = metadata is not None

        # Build the LangChain chain for this request
        chain = create_para_chain(include_metadata=include_metadata)

        # Assemble input dict via helper (handles metadata merging)
        input_data = _build_langchain_input(text, metadata)

        # Invoke the chain (Prompt -> LLM -> JsonOutputParser)
        result = chain.invoke(input_data)

        logger.info(
            "Classification complete: %s (confidence: %.2f%%, with_metadata: %s)",
            result["category"],
            result["confidence"] * 100,
            include_metadata,
        )

        return {
            "category": result["category"],
            "confidence": result["confidence"],
            "reasoning": result["reasoning"],
            "detected_cues": result.get("detected_cues", []),
            "source": "langchain",
            "has_metadata": include_metadata,
        }

    except (
        OutputParserException,
        openai.APITimeoutError,
        openai.RateLimitError,
        openai.APIConnectionError,
        openai.APIStatusError,
        OSError,
    ) as exc:
        # Catch specific LLM API and I/O failures; re-raise after structured logging
        meta = build_meta({"action": "classify_with_langchain"})
        log_agent_error(logger, "LangChain classification failed", exc, meta)
        raise


# ============================================================
# 메타데이터 기반 PARA 분류 (새로 추가)
# ============================================================


def get_metadata_classification_prompt() -> str:
    """메타데이터 분류 프롬프트 파일 읽기"""
    prompt_path = CLASSIFIER_DIR / "prompts" / "metadata_classification_prompt.txt"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Escape all braces except the {metadata} template variable
        lines = []
        for line in content.split("\n"):
            if "{metadata}" not in line:
                # Escape all other braces for PromptTemplate compatibility
                line = line.replace("{", "{{").replace("}", "}}")
                # Restore {metadata} after the blanket escape
                line = line.replace("{{metadata}}", "{metadata}")
            # Leave lines containing the template variable {metadata} untouched
            lines.append(line)

        return "\n".join(lines)
    except FileNotFoundError:
        # Log only the filename to avoid exposing absolute paths (PII protection)
        logger.error("Metadata prompt file not found: %s", prompt_path.name)
        raise


def create_metadata_classification_chain():
    """메타데이터 기반 PARA 분류 Chain 생성"""
    prompt_content = get_metadata_classification_prompt()

    prompt = PromptTemplate(input_variables=["metadata"], template=prompt_content)

    llm = ChatOpenAI(
        api_key=ModelConfig.GPT4O_MINI_API_KEY,
        base_url=ModelConfig.GPT4O_MINI_BASE_URL,
        model=ModelConfig.GPT4O_MINI_MODEL,
        temperature=0.0,  # 메타데이터는 deterministic
        max_tokens=500,
    )

    parser = JsonOutputParser(pydantic_object=PARAClassificationOutput)
    return prompt | llm | parser


def classify_with_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    메타데이터만을 사용해 PARA로 분류

    Args:
        metadata: 메타데이터 딕셔너리 (JSON 형식)
        {
            "basic_info": {...},
            "temporal_info": {...},
            ...
        }

    Returns:
        Dict: 분류 결과
        {
            "category": str,
            "confidence": float,
            "reasoning": str,
            "detected_cues": List[str],
            "source": str,
            "metadata_used": bool
        }
    """
    try:
        # Build the metadata-only classification chain
        chain = create_metadata_classification_chain()

        # Serialize metadata dict to a JSON string for the prompt template
        metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)

        # Invoke the chain
        result = chain.invoke({"metadata": metadata_json})

        logger.info(
            "Metadata classification complete: %s (confidence: %.2f%%)",
            result["category"],
            result["confidence"] * 100,
        )

        return {
            "category": result["category"],
            "confidence": result["confidence"],
            "reasoning": result["reasoning"],
            "detected_cues": result.get("detected_cues", []),
            "source": "metadata",
            "metadata_used": True,
        }

    except (
        OutputParserException,
        openai.APITimeoutError,
        openai.RateLimitError,
        openai.APIConnectionError,
        openai.APIStatusError,
        OSError,
    ) as exc:
        # Catch specific LLM API and I/O failures; re-raise after structured logging
        meta = build_meta({"action": "classify_with_metadata"})
        log_agent_error(logger, "Metadata classification failed", exc, meta)
        raise


def hybrid_classify(text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    텍스트와 메타데이터 모두를 사용해 하이브리드 분류

    Args:
        text: 분류할 텍스트
        metadata: 메타데이터 딕셔너리

    Returns:
        Dict: 통합 분류 결과
        {
            "category": str,
            "confidence": float,
            "reasoning": str,
            "text_result": {...},
            "metadata_result": {...},
            "merge_strategy": str,
            "source": str
        }
    """
    try:
        # Step 1: text-based classification
        text_result = classify_with_langchain(text)

        # Step 2: metadata-based classification
        metadata_result = classify_with_metadata(metadata)

        # Step 3: merge results using a confidence-weighted strategy
        final_category, final_confidence, merge_strategy = _merge_confidence_weighted(
            text_result, metadata_result
        )

        logger.info(
            "Hybrid classification: %s (strategy: %s, confidence: %.2f%%)",
            final_category,
            merge_strategy,
            final_confidence * 100,
        )

        return {
            "category": final_category,
            "confidence": final_confidence,
            "reasoning": f"Text: {text_result['reasoning']} | Meta: {metadata_result['reasoning']}",
            "text_result": text_result,
            "metadata_result": metadata_result,
            "merge_strategy": merge_strategy,
            "source": "hybrid",
        }

    except (
        OutputParserException,
        openai.APITimeoutError,
        openai.RateLimitError,
        openai.APIConnectionError,
        openai.APIStatusError,
        OSError,
    ) as exc:
        # Propagate specific LLM / IO failures with structured logging
        meta = build_meta({"action": "hybrid_classify"})
        log_agent_error(logger, "Hybrid classification failed", exc, meta)
        raise


# 테스트용
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("Config 기반 LangChain 테스트")
    print("=" * 60)
    print(
        f"API Key: {ModelConfig.GPT4O_MINI_API_KEY[:3]}..."
        if ModelConfig.GPT4O_MINI_API_KEY
        else "❌ API Key 없음"
    )
    print(
        f"API Base: {ModelConfig.GPT4O_MINI_BASE_URL[:3]}..................."
        if ModelConfig.GPT4O_MINI_BASE_URL
        else "❌ API Base 못찾음"
    )
    print(
        f"Model: {ModelConfig.GPT4O_MINI_MODEL}"
        if ModelConfig.GPT4O_MINI_MODEL
        else "❌ Model 없음"
    )
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
        "tags": ["work", "important"],
    }

    print("\n" + "=" * 60)
    print("테스트 2: 메타데이터 포함 분류")
    print("=" * 60)

    try:
        result = classify_with_langchain(test_text_2, metadata=test_metadata)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"오류: {e}")

    # 추가
    # 테스트 3: 메타데이터만 분류 (새로운 함수)
    print("\n" + "=" * 60)
    print("테스트 3: 메타데이터만 분류")
    print("=" * 60)

    test_metadata = {
        "basic_info": {
            "title": "2024년 완료된 프로젝트 보고서",
            "summary": "지난해 프로젝트들의 최종 결과",
            "content_type": "report",
        },
        "temporal_info": {
            "created_date": "2024-12-31",
            "deadline": None,
            "status": "completed",
        },
    }

    try:
        result = classify_with_metadata(test_metadata)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"오류: {e}")

    # 테스트 4: 하이브리드 분류 (새로운 함수)
    print("\n" + "=" * 60)
    print("테스트 4: 하이브리드 분류 (텍스트 + 메타데이터)")
    print("=" * 60)

    test_text = "다음 분기 마케팅 캠페인"
    test_metadata = {
        "basic_info": {
            "title": "Q2_Marketing_Campaign_2025.md",
            "created_date": "2025-11-01",
        },
        "temporal_info": {"deadline": "2025-06-30", "status": "planning"},
    }

    try:
        result = hybrid_classify(test_text, test_metadata)
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


"""test_result_2(metadata_prompt용)

    ✅ ModelConfig loaded from backend.config

    ============================================================
    Config 기반 LangChain 테스트
    ============================================================
    API Key: eyJ...
    API Base: htt...................
    Model: openai/gpt-4o-mini
    ============================================================

    ============================================================
    테스트 3: 메타데이터만 분류
    ============================================================
    INFO:httpx:HTTP Request: POST https:****** "HTTP/1.1 200 OK"
    INFO:__main__:메타데이터 분류 완료: Archives (confidence: 95.00%)
    {
        "category": "Archives",
        "confidence": 0.95,
        "reasoning": "status가 'completed'로 명시되어 있으며, action_items이 없고, 과거 날짜로 설정되어 있어 Archives로 분류됩니다.",
        "detected_cues": [
            "status: completed"
        ],
        "source": "metadata",
        "metadata_used": true
    }

    ============================================================
    테스트 4: 하이브리드 분류 (텍스트 + 메타데이터)
    ============================================================
    INFO:httpx:HTTP Request: POST https:****** "HTTP/1.1 200 OK"
    INFO:__main__:분류 완료: Projects (confidence: 90.00%, metadata: False)
    INFO:httpx:HTTP Request: POST https:****** "HTTP/1.1 200 OK"
    INFO:__main__:메타데이터 분류 완료: Projects (confidence: 90.00%)
    INFO:__main__:하이브리드 분류: Projects (strategy: text_dominant (0.7:0.3), confidence: 90.00%)
    {
        "category": "Projects",
        "confidence": 0.9,
        "reasoning": "텍스트: 다음 분기라는 시간 표현과 마케팅 캠페인이라는 구체적 목표가 있어 Projects로 분류됨. | 메타: status가 'planning'이며, deadline이 존재하여 명확한 프로젝트로 분류됩니다.",
        "text_result": {
            "category": "Projects",
            "confidence": 0.9,
            "reasoning": "다음 분기라는 시간 표현과 마케팅 캠페인이라는 구체적 목표가 있어 Projects로 분류됨.",
            "detected_cues": [
                "다음 분기",
                "마케팅 캠페인"
            ],
            "source": "langchain",
            "has_metadata": false
    },
    "metadata_result": {
        "category": "Projects",
        "confidence": 0.9,
        "reasoning": "status가 'planning'이며, deadline이 존재하여 명확한 프로젝트로 분류됩니다.",
        "detected_cues": [
            "status: planning",
            "deadline: 2025-06-30"
        ],
        "source": "metadata",
        "metadata_used": true
    },
    "merge_strategy": "text_dominant (0.7:0.3)",
    "source": "hybrid"
    }

"""

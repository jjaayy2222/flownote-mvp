from typing import Literal, Dict, Any, List, Optional
import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from backend.agent.state import AgentState
from backend.agent.utils import get_llm, extract_keywords, search_similar_docs

# =================================================================
# Logger Setup
# =================================================================
logger = logging.getLogger(__name__)

# =================================================================
# Constants
# =================================================================
CONFIDENCE_THRESHOLD = 0.7
MAX_RETRY_COUNT = 3


# =================================================================
# Pydantic Models for Output Parsing
# =================================================================
class ClassificationOutput(BaseModel):
    category: str = Field(
        description="The PARA category (Projects, Areas, Resources, Archives)"
    )
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(description="Reasoning for the classification")


# =================================================================
# Node Functions
# =================================================================


def analyze_node(state: AgentState) -> Dict[str, Any]:
    """
    입력 분석 노드: 문서 내용에서 핵심 키워드 추출
    """
    # 안전한 접근 (데이터 누락 시 빈 문자열 처리하여 에러 방지)
    content = state.get("file_content", "")
    keywords = extract_keywords(content)
    # State 업데이트: extracted_keywords
    return {"extracted_keywords": keywords}


def retrieve_node(state: AgentState) -> Dict[str, Any]:
    """
    맥락 검색 노드: 키워드 기반 유사 문서 검색 (RAG)
    """
    # NotRequired 필드 안전한 접근
    keywords = state.get("extracted_keywords", [])

    # 헬퍼 함수 호출 (Stub -> Mock)
    context = search_similar_docs(keywords)
    # State 업데이트: retrieved_context
    return {"retrieved_context": context}


def classify_node(state: AgentState) -> Dict[str, Any]:
    """
    분류 수행 노드: LLM을 사용하여 PARA 카테고리 분류
    """
    llm = get_llm()

    # LLM 초기화 실패 시 Stub 반환 (안전장치)
    if not llm:
        return {
            "classification_result": {"category": "Resources", "confidence": 0.0},
            "confidence_score": 0.0,
            "reasoning": "LLM initialization failed (Stub)",
        }

    # Prompt Template
    template = """
    You are an expert document classifier.
    Your task is to classify the following document into one of the PARA method categories:
    - Projects: Active tasks and projects with a deadline.
    - Areas: Ongoing responsibilities without a deadline.
    - Resources: Topics or themes of ongoing interest.
    - Archives: Completed or inactive items.

    Use the provided extracted keywords and retrieved context to aid your decision.
    
    File Name: {file_name}
    Extracted Keywords: {keywords}
    Retrieved Context: {context}
    
    Document Content (Snippet):
    {content}
    
    {format_instructions}
    """

    # Pydantic Output Parser 설정
    try:
        parser = PydanticOutputParser(pydantic_object=ClassificationOutput)

        # 포맷 지침을 포함한 프롬프트 생성
        prompt = ChatPromptTemplate.from_template(
            template,
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )

        # 체인 연결: Prompt -> LLM -> Parser
        chain = prompt | llm | parser

        # 입력 데이터 준비 및 길이 제한
        content_snippet = state.get("file_content", "")[:3000]
        keywords_str = ", ".join(state.get("extracted_keywords", []))
        context_str = state.get("retrieved_context", "")

        # 체인 실행
        result = chain.invoke(
            {
                "file_name": state.get("file_name", "Unknown"),
                "keywords": keywords_str,
                "context": context_str,
                "content": content_snippet,
            }
        )

        # Pydantic 모델 -> Dict 변환 (AgentState 호환)
        return {
            "classification_result": {
                "category": result.category,
                "confidence": result.confidence,
            },
            "confidence_score": result.confidence,
            "reasoning": result.reasoning,
        }

    except Exception as e:
        logger.error("Error in classification", exc_info=True)
        # 실패 시 Stub 반환 (안전장치)
        # 실제 운영 환경에서는 에러를 로깅하고 재시도하거나 사용자에게 알림
        return {
            "classification_result": {"category": "Unclassified", "confidence": 0.0},
            "confidence_score": 0.0,
            "reasoning": f"Classification error: {str(e)}",
        }


def validate_node(state: AgentState) -> Dict[str, Any]:
    """
    검증 노드: 분류 결과의 신뢰도 및 형식 검사
    """
    # 검증 로직 구현 (현재는 항상 통과 가정)
    return {}


def reflect_node(state: AgentState) -> Dict[str, Any]:
    """
    회고 노드: 낮은 신뢰도 원인 분석 및 재시도 카운트 증가
    """
    # 재시도 횟수 증가 (안전한 접근)
    current_count = state.get("retry_count", 0)
    return {"retry_count": current_count + 1}


# =================================================================
# Conditional Edges
# =================================================================


def should_retry(state: AgentState) -> Literal["end", "retry"]:
    """
    재시도 여부 결정 (Conditional Edge)

    Returns:
        Literal["end", "retry"]: 종료 또는 재시도 경로
    """
    confidence = state.get("confidence_score", 0.0)
    retry_count = state.get("retry_count", 0)

    # 1. 신뢰도가 충분히 높으면 종료
    if confidence >= CONFIDENCE_THRESHOLD:
        return "end"

    # 2. 최대 재시도 횟수 초과 시 종료
    if retry_count >= MAX_RETRY_COUNT:
        return "end"

    # 3. 그 외의 경우 재시도 (Reflection 노드로 이동)
    return "retry"

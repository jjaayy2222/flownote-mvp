# backend/agent/nodes.py

from typing import Literal, Dict, Any, List, Optional
from backend.agent.state import AgentState
from backend.agent.utils import get_llm, extract_keywords, search_similar_docs

# =================================================================
# Node Functions
# =================================================================


def analyze_node(state: AgentState) -> Dict[str, Any]:
    """
    입력 분석 노드: 문서 내용에서 핵심 키워드 추출
    """
    # 헬퍼 함수 호출 (Stub)
    # file_content는 Required 필드이므로 직접 접근 가능
    keywords = extract_keywords(state["file_content"])
    # State 업데이트: extracted_keywords
    return {"extracted_keywords": keywords}


def retrieve_node(state: AgentState) -> Dict[str, Any]:
    """
    맥락 검색 노드: 키워드 기반 유사 문서 검색 (RAG)
    """
    # NotRequired 필드 안전한 접근
    keywords = state.get("extracted_keywords", [])

    # 헬퍼 함수 호출 (Stub)
    context = search_similar_docs(keywords)
    # State 업데이트: retrieved_context
    return {"retrieved_context": context}


def classify_node(state: AgentState) -> Dict[str, Any]:
    """
    분류 수행 노드: LLM을 사용하여 PARA 카테고리 분류
    """
    llm = get_llm()

    if not llm:
        # Stub: LLM 미설정 시 기본값 반환
        return {
            "classification_result": {"category": "Resources", "confidence": 0.0},
            "confidence_score": 0.0,
            "reasoning": "LLM not initialized (Stub)",
        }

    # TODO: 실제 LLM 호출 및 Pydantic 파싱 로직 구현
    # result = llm.invoke(...)
    # return result.dict()

    # 임시 Stub (구현 전까지 유지)
    return {
        "classification_result": {"category": "Projects", "confidence": 0.0},
        "confidence_score": 0.0,
        "reasoning": "LLM implementation pending",
    }


def validate_node(state: AgentState) -> Dict[str, Any]:
    """
    검증 노드: 분류 결과의 신뢰도 및 형식 검사
    """
    # 검증 로직 구현 (현재는 항상 통과 가정)
    # State 변경 없음
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
    if confidence >= 0.7:
        return "end"

    # 2. 최대 재시도 횟수 초과 시 종료
    if retry_count >= 3:
        return "end"

    # 3. 그 외의 경우 재시도 (Reflection 노드로 이동)
    return "retry"

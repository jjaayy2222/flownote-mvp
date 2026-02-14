# backend/agent/utils.py

from typing import List, Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

# 실제 구현 시 필요한 라이브러리 임포트 (TODO)
# from langchain_openai import ChatOpenAI


def get_llm() -> Optional["BaseChatModel"]:
    """
    LLM 인스턴스를 반환하는 팩토리 함수 (Stub)

    Returns:
        Optional[BaseChatModel]: 초기화된 LLM 인스턴스 (현재는 None 반환)
    """
    # TODO: 실제 구현 시 ChatOpenAI 인스턴스 반환 및 설정
    # llm = ChatOpenAI(model="gpt-4o", temperature=0)
    # return llm
    return None


def extract_keywords(text: str) -> List[str]:
    """
    텍스트에서 핵심 키워드를 추출하는 함수 (Stub)

    Args:
        text (str): 분석할 문서 내용

    Returns:
        List[str]: 추출된 키워드 리스트 (현재는 빈 리스트 반환)
    """
    # TODO: 키워드 추출 로직 구현 (LLM 활용 또는 정규식/NLP 라이브러리)
    return []


def search_similar_docs(keywords: List[str]) -> str:
    """
    키워드 기반 유사 문서를 검색하는 함수 (Stub)

    Args:
        keywords (List[str]): 검색 키워드 리스트

    Returns:
        str: 검색된 유사 문서 내용 (현재는 빈 문자열 반환)
    """
    # TODO: 벡터 DB 연동 및 검색 로직 구현
    # RAG 파이프라인 연결 예정
    return ""

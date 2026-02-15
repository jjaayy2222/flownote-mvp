import os
import re
import logging
from typing import List, Optional, TYPE_CHECKING, Any
from functools import lru_cache

from dotenv import load_dotenv

# 로컬 환경 변수 로드 (.env 파일이 없으면 무시됨)
load_dotenv()

# 로거 설정
logger = logging.getLogger(__name__)

# 정규식 패턴 사전 컴파일 (Module Level Constant)
# 목적: 매 호출마다의 컴파일 오버헤드 제거
# 패턴: 영어(대문자 시작/긴 단어) 또는 한글(2글자 이상)
KEYWORD_PATTERN = r"\b[A-Za-z][a-z]{4,}\b|\b[A-Z][a-zA-Z]+\b|[가-힣]{2,}"
KEYWORD_REGEX = re.compile(KEYWORD_PATTERN)

# 타입 힌팅용 임포트 (런타임 영향 최소화)
if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
else:
    try:
        from langchain_core.language_models import BaseChatModel
    except ImportError:
        # 런타임에 의존성이 없을 경우를 대비한 더미 클래스
        class BaseChatModel:
            pass


# 실제 런타임용 라이브러리 임포트
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import CommaSeparatedListOutputParser
except ImportError:
    # 패키지 미설치 시 None 처리 (함수 내에서 핸들링)
    ChatOpenAI = None  # type: ignore
    ChatPromptTemplate = None  # type: ignore
    CommaSeparatedListOutputParser = None  # type: ignore


@lru_cache(maxsize=1)
def get_llm() -> Optional["BaseChatModel"]:
    """
    LLM 인스턴스를 반환하는 팩토리 함수.
    LRU Cache를 사용하여 인스턴스 재생성을 방지하고 오버헤드를 줄입니다.
    """
    if ChatOpenAI is None:
        logger.warning("langchain_openai not installed.")
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not found in environment variables.")
        return None

    try:
        # 분류 및 추출 작업에는 결정적인 출력을 위해 temperature=0 사용
        return ChatOpenAI(model="gpt-4o", temperature=0)
    except Exception as e:
        logger.error("Error initializing LLM", exc_info=True)
        return None


def extract_keywords(text: str) -> List[str]:
    """
    문서에서 핵심 키워드를 추출하는 함수.
    1차적으로 LLM을 시도하고, 실패 시 정규식 기반 폴백 로직을 수행합니다.
    """
    llm = get_llm()

    # 텍스트가 너무 짧거나 LLM이 없으면 폴백
    if not llm or not text or len(text.strip()) < 10:
        return _extract_keywords_regex(text)

    try:
        # Prompt Template 정의
        template = """
        Analyze the following text and extract 5 to 10 key topics or keywords that best describe its content.
        The keywords should be relevant for categorizing the document into PARA (Projects, Areas, Resources, Archives).
        Return purely a comma-separated list of keywords, nothing else.
        
        Text:
        {text}
        
        Keywords:
        """

        prompt = ChatPromptTemplate.from_template(template)
        # CommaSeparatedListOutputParser는 문자열 리스트를 반환합니다.
        chain = prompt | llm | CommaSeparatedListOutputParser()

        # 텍스트 길이 제한 (토큰 비용 절감 및 컨텍스트 윈도우 보호)
        keywords = chain.invoke({"text": text[:3000]})
        return [k.strip() for k in keywords if k.strip()]

    except Exception as e:
        logger.error("Error extracting keywords with LLM", exc_info=True)
        return _extract_keywords_regex(text)


def _extract_keywords_regex(text: str) -> List[str]:
    """
    정규식을 사용한 간단한 키워드 추출 (Fallback Logic).
    결정적인(Deterministic) 순서를 보장하기 위해 set 대신 dict.fromkeys를 사용하여 중복을 제거합니다.
    """
    if not text:
        return []

    # 미리 컴파일된 정규식 사용 (Performance Optimization)
    words = KEYWORD_REGEX.findall(text)

    # 중복 제거 (순서 유지) 및 상위 10개 반환
    # Python 3.7+ 에서는 dict insertion order가 보장됨
    unique_words = list(dict.fromkeys(words))
    return unique_words[:10]


def search_similar_docs(keywords: List[str]) -> str:
    """
    키워드 기반 유사 문서를 검색하는 함수 (Mock Implementation).
    현재는 실제 Vector Store가 없으므로 검색된 척하는 더미 데이터를 반환합니다.
    """
    if not keywords:
        return ""

    # Mock Response: 키워드가 포함된 가상의 문서를 반환하여 RAG 흐름 테스트
    docs = [
        f"- Document related to '{k}' explicitly mentioning project deadlines."
        for k in keywords[:3]
    ]

    if not docs:
        return "No relevant documents found."

    return "Retrieved Context:\n" + "\n".join(docs)

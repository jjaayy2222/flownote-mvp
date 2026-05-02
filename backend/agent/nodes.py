from typing import Literal, Dict, Any, List, Optional, AsyncGenerator, Protocol
import logging
from functools import lru_cache
from contextlib import asynccontextmanager
from backend.agent.state import AgentState
from backend.agent.utils import get_llm, extract_keywords, search_similar_docs, resolve_active_model
from backend.agent.constants import EMPTY_RETRIEVED_CONTEXT

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from backend.services.hybrid_search_service import HybridSearchService
from backend.services.topic_clustering_service import cluster_user_topics

# Try importing specific exceptions for better error handling
try:
    from langchain_core.exceptions import OutputParserException
except ImportError:
    # 런타임에 의존성이 구버전이거나 없을 경우를 대비한 더미 클래스
    class OutputParserException(Exception):
        pass


# =================================================================
# Logger Setup
# =================================================================
logger = logging.getLogger(__name__)

# =================================================================
# Constants
# =================================================================
# Used in conditional edges (should_retry) logic
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


@lru_cache(maxsize=1)
def _get_hybrid_search_service() -> HybridSearchService:
    """HybridSearchService의 싱글톤 인스턴스를 반환합니다."""
    return HybridSearchService()


def cleanup_hybrid_search_service() -> None:
    """
    싱글톤 HybridSearchService 인스턴스를 초기화(캐시 해제)합니다.
    """
    _get_hybrid_search_service.cache_clear()


class LifespanApp(Protocol):
    """
    FastAPI 등 수명 주기 매니저를 호출하는 애플리케이션 프레임워크의 최소 요구 인터페이스입니다.
    현재 `managed_hybrid_search_async` 내부에서는 애플리케이션의 특정 속성을 참조하지 않으므로 
    비어있는 상태(빈 프로토콜)로 정의되어 결합도를 최소화합니다.
    """
    pass


@asynccontextmanager
async def managed_hybrid_search_async(_app: LifespanApp | None = None, **_kwargs: Any) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan 등 장기 실행 애플리케이션에 주입하여 하이브리드 검색 싱글톤의 수명 주기를 
    코드 레벨에서 안전하게 보장하는 비동기 컨텍스트 매니저 헬퍼입니다.
    
    [매개변수 설계 안내]
    - `_app: LifespanApp | None`: IDE 자동완성 및 정적 타입 힌팅을 제공하기 위한 주 매개변수 명시.
      (사용하지 않는 인자임을 명확히 하기 위해 `_` 접두사를 사용하였으며, Any 대신 빈 Protocol을 
       사용하여 프레임워크 종속성 없이 타입 안정성 확보)
    - `**_kwargs: Any`: FastAPI lifespan 등 외부 프레임워크가 임의로 주입할 수 있는 
      추가 인자를 에러 없이 수용(Tolerant)하기 위한 안전장치입니다. (제거하지 마세요)
    
    사용 예시:
    ```python
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with managed_hybrid_search_async():
            # 시스템 기동
            yield
        # 시스템 종료 시 자동으로 cleanup_hybrid_search_service 호출
    ```
    """
    try:
        yield
    finally:
        cleanup_hybrid_search_service()


def _build_query_from_keywords(keywords: list[str]) -> str:
    return " ".join(keywords)


def _inject_topics_into_query(query: str, clusters: list[dict[str, Any]]) -> str:
    topic_labels = [c["label"] for c in clusters if "label" in c]
    if not topic_labels:
        return query
    topics_str = ", ".join(topic_labels)
    return f"[{topics_str}] {query}"


_MAX_ITEMS = 5
_MAX_CHARS_PER_ITEM = 500
_MAX_TOTAL_CHARS = 4000

def _format_rrf_results(rrf_result) -> str:
    """
    RRF 결과를 LLM 입력에 적합한 간결한 컨텍스트 문자열로 포맷팅합니다.
    """
    # 제너레이터/이터러블 1회 소진 및 len() 호출 시 TypeError 방지를 위해 명시적으로 리스트화합니다.
    raw_results = getattr(rrf_result, "results", None) or []
    results = list(raw_results)
    
    if not results:
        return "No relevant documents found."

    formatted_docs: list[str] = []
    total_len = len("Retrieved Context:\n")

    for idx, res in enumerate(results):
        if idx >= _MAX_ITEMS:
            break

        item = res.get("item", {}) if isinstance(res, dict) else getattr(res, "item", {})
        if not isinstance(item, dict):
            content = str(item)
        else:
            content = item.get("content") or str(item)

        if len(content) > _MAX_CHARS_PER_ITEM:
            content = content[: _MAX_CHARS_PER_ITEM - 3] + "..."

        line = f"- {content}"
        
        if total_len + len(line) + 1 > _MAX_TOTAL_CHARS:
            break

        formatted_docs.append(line)
        total_len += len(line) + 1

    if not formatted_docs:
        return "No relevant documents found."

    result_str = "Retrieved Context:\n" + "\n".join(formatted_docs)

    omitted_count = len(results) - len(formatted_docs)
    if omitted_count > 0:
        notice = f"\n- [{omitted_count} additional retrieved documents omitted for brevity]"
        if len(result_str) + len(notice) <= _MAX_TOTAL_CHARS:
            result_str += notice
        else:
            # 예산이 부족해도 관측성 확보를 위해 최소한의 알림 추가
            short_notice = f"\n- [...{omitted_count} more]"
            result_str += short_notice

    return result_str


async def _run_hybrid_search(hashed_user_id: str, query: str, clusters: list[dict[str, Any]]) -> str:
    query_with_topics = _inject_topics_into_query(query, clusters)

    hybrid_service = _get_hybrid_search_service()
    router_result = await hybrid_service.route_weighted_search(
        hashed_user_id=hashed_user_id,
        query=query_with_topics,
    )
    rrf_result = hybrid_service.merge_with_rrf(router_result)
    return _format_rrf_results(rrf_result)


async def retrieve_node(state: AgentState) -> Dict[str, Any]:
    """
    맥락 검색 노드: 키워드 기반 유사 문서 검색 (RAG)
    """
    keywords = state.get("extracted_keywords", [])
    
    # 불필요한 함수 호출(search_similar_docs)을 방지하고 중립적인 빈 문자열을 즉시 반환(단락 평가)
    if not keywords:
        logger.debug("[HYBRID_SEARCH] 키워드가 없어 빈 검색 결과를 반환합니다.")
        return {"retrieved_context": EMPTY_RETRIEVED_CONTEXT}
        
    query = _build_query_from_keywords(keywords)
    hashed_user_id = state.get("hashed_user_id")

    if not hashed_user_id:
        logger.info("[HYBRID_SEARCH] hashed_user_id 누락. 전역 검색으로 폴백합니다.")
        context = search_similar_docs(keywords)
        return {"retrieved_context": context}

    # 1. 클러스터링 시도
    clusters = []
    try:
        clusters_res = await cluster_user_topics(hashed_user_id)
        if clusters_res:
            clusters = clusters_res
    except Exception:
        logger.warning(
            "[HYBRID_SEARCH] 토픽 클러스터링 실패. 개인화 컨텍스트 없이 하이브리드 검색을 계속합니다.",
            exc_info=True,
        )

    # 2. 하이브리드 검색 시도
    try:
        context = await _run_hybrid_search(hashed_user_id, query, clusters)
    except Exception:
        logger.error(
            "[HYBRID_SEARCH] 라우터 호출 실패. 전역 인덱스 검색으로 Graceful Degradation 처리합니다.",
            exc_info=True,
        )
        context = search_similar_docs(keywords)

    return {"retrieved_context": context}


async def classify_node(state: AgentState) -> Dict[str, Any]:
    """
    분류 수행 노드: LLM을 사용하여 PARA 카테고리 분류
    """
    model_name = await resolve_active_model()

    llm = get_llm(model_name)

    # LLM 초기화 실패 시 Stub 반환 (안전장치)
    if not llm:
        logger.warning("LLM not initialized, returning Stub for classify_node")
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

    try:
        # Pydantic Output Parser 설정
        parser = PydanticOutputParser(pydantic_object=ClassificationOutput)

        # 포맷 지침을 포함한 프롬프트 생성 (Standard LangChain Pattern: .partial chaining)
        # partial_variables를 직접 인자로 넘기는 것보다 명시적인 체이닝을 권장합니다.
        prompt = ChatPromptTemplate.from_template(template).partial(
            format_instructions=parser.get_format_instructions()
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

    except OutputParserException as e:
        logger.error("Parsing Error in classification", exc_info=True)
        # 파싱 에러 시 명확한 사유와 함께 실패 처리 (재시도 로직에서 활용 가능)
        return {
            "classification_result": {"category": "Unclassified", "confidence": 0.0},
            "confidence_score": 0.0,
            "reasoning": f"Output Parsing Error: {str(e)}. Response format invalid.",
        }

    except Exception as e:
        logger.error("Unexpected Error in classification", exc_info=True)
        # 그 외 예상치 못한 에러에 대한 안전장치 (Fail-safe)
        return {
            "classification_result": {"category": "Unclassified", "confidence": 0.0},
            "confidence_score": 0.0,
            "reasoning": f"Unexpected Classification error: {str(e)}",
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

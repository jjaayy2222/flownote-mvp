# backend/agent/chat/tools.py

import logging
from typing import Any, Dict, Optional, TypedDict, cast
from langchain_core.tools import tool  # type: ignore[import, import-untyped, reportMissingImports]
from backend.services.hybrid_search_service import get_hybrid_search_service  # type: ignore[import, import-untyped, reportMissingImports]

import os
import asyncio
from tavily import TavilyClient

logger = logging.getLogger(__name__)

# 도구 내 단일 문서 최대 길이 상수 (하드코딩 방지)
_MAX_DOC_CONTENT_CHARS = 1_000
# [Security] 로그에 포함되는 doc_id의 최대 길이 제한 (PII 경계값 명시)
_MAX_LOG_DOC_ID_LEN = 50

_tavily_client: Optional[TavilyClient] = None

def _get_tavily_client(api_key: str) -> TavilyClient:
    """
    Lazily initialize and reuse a module-level TavilyClient instance.

    This avoids constructing a new client for every deep_web_search_tool call
    while preserving the existing per-call API key validation and error handling.
    """
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


class SerializedDoc(TypedDict):
    """
    JSON 직렬화 가능한 정규화된 문서 구조.

    [Contract] 이 TypedDict의 모든 필드는 실제로 JSON 직렬화 가능한 원시 타입으로
    _normalize_doc를 통해 강제(타입 코어션)될 때만 생성되어야 합니다.

    - `id`      : 문서의 식별자. 원칙적으로 str로 저장되며, 없는 경우 None.
    - `score`   : 검색 점수. 원칙적으로 float로 저장되며, 파싱이 불가한 경우 None.
    - `content` : 문서 본문. 항상 str. None 입력 시 ''(empty string)으로 폴백.
    - `metadata`: 원본 메타데이터 dict. 로우 레벨 필드는 Any를 허용하지만,
                  모든 값은 직렬화 시 json.dumps(기본값 default=str)로 방어됨.
    """
    id: Optional[str]
    score: Optional[float]
    content: str
    metadata: Dict[str, Any]


def _build_log_extra(doc_id: Optional[str], **kwargs: Any) -> Dict[str, Any]:
    """
    운영 로그용 extra 페이로드를 표준화하여 반환합니다.

    doc_id를 모든 경고 로깅에 포함하면 발생 문서를 로그만으로 추적할 수 있습니다.
    **kwargs로 상황별 추가 필드(metadata_type, score_type 등)를 자유롭게 추가합니다.
    """
    return {"doc_id": doc_id, **kwargs}


def _normalize_doc(doc: Any) -> SerializedDoc:
    """
    검색 결과 문서(dict 또는 LangChain Document 유사 객체)를
    JSON 직렬화 가능한 SerializedDoc로 정규화하여 반환합니다.

    [Contract 실제 구현 보장]
    - `id`      : str로 코어션. 없거나 None인 경우만 None 유지.
    - `score`   : float로 코어션. 파싱 불가한 입력 시 None으로 폴백 (예외 없이).
    - `content` : str로 코어션. None 입력 시 ''(empty string)로 폴백.
    - `metadata`: dict 100% 부보. None 또는 비-dict 입력 시 {} 폴백.

    Args:
        doc: dict 또는 .page_content / .metadata / .id / .score 속성을 갖는 객체.
    """
    is_dict = isinstance(doc, dict)

    # --- id 정규화: Optional[str] — metadata 경고 로깅 콘텍스트를 위해 먼저 추출 ---
    raw_id = doc.get("id") if is_dict else getattr(doc, "id", None)
    normalized_id: Optional[str] = str(raw_id) if raw_id is not None else None
    # [주의] normalized_id는 위 63행에서 str(raw_id)로 코어션되었으므로 항상 str | None.
    # → isinstance(normalized_id, str)은 사실상 "normalized_id is not None"과 동일.
    # → int, UUID 등 비-str raw_id도 이미 str()로 변환된 뒤 이 가드에 도달하므로 로깅에서 탈락하지 않음.
    # [Security] _MAX_LOG_DOC_ID_LEN으로 잘라 PII 방지.
    # type: ignore[index]: isinstance(str) 블록 내에서도 Pyre2가 str 슬라이스를 오판단하는 알려진 False Positive.
    if isinstance(normalized_id, str):
        _doc_id_for_log: Optional[str] = normalized_id[:_MAX_LOG_DOC_ID_LEN]  # type: ignore[index]
    else:
        # raw_id가 None이었을 때만 이 분기에 도달 (str() 코어션 보장에 의해 str 탈락 없음)
        _doc_id_for_log = None

    # --- content 정규화: str 보장 ---
    raw_content = (
        doc.get("content", "")
        if is_dict
        else getattr(doc, "page_content", getattr(doc, "content", ""))
    )
    content: str = str(raw_content) if raw_content is not None else ""

    # --- metadata 정규화: dict 보장 ---
    raw_metadata = doc.get("metadata", {}) if is_dict else getattr(doc, "metadata", {})
    if isinstance(raw_metadata, dict):
        metadata: Dict[str, Any] = raw_metadata
    else:
        # 업스트림 스키마 변경이나 오류를 조기에 탐지하기 위해 경고 로깅 (doc_id 식별 콘텍스트 포함)
        logger.warning(
            "[Tool] metadata가 dict가 아닌 타입. 빈 dict로 폴백",
            extra=_build_log_extra(
                _doc_id_for_log,
                metadata_type=type(raw_metadata).__name__,
            ),
        )
        metadata = {}

    # --- score 정규화: Optional[float] ---
    raw_score = doc.get("score") if is_dict else getattr(doc, "score", None)
    normalized_score: Optional[float]
    if raw_score is None:
        normalized_score = None
    else:
        try:
            normalized_score = float(raw_score)
        except (ValueError, TypeError):
            logger.warning(
                "[Tool] score 정규화 실패, None으로 폴백",
                extra=_build_log_extra(
                    _doc_id_for_log,
                    score_type=type(raw_score).__name__,
                ),
            )
            normalized_score = None

    # [Engineering Decision] Python TypedDict의 구조적 한계로 인해 반환 시 dict 리터럴은
    # 타입 체커가 SerializedDoc 계약을 자동 검증하지 않습니다.
    # 이 cast는 해당 단언이 필요하지만, 부정확한 cast가 아닙니다:
    # 반환 지점에 도달하는 모든 필드(normalized_id, normalized_score, content, metadata)는
    # 각각 위에서 명시적으로 타입 어노테이션되었으므로 mypy가 해당 시점까지 개별 유효성을 검증합니다.
    return cast(SerializedDoc, {
        "id": normalized_id,
        "score": normalized_score,
        "content": content,
        "metadata": metadata,
    })


@tool
async def search_documents_tool(query: str, k: int = 5) -> dict:
    """
    RAG 기반 사내 문서 검색 도구입니다.
    사용자의 질문이나 분석 의도와 관련된 지식 베이스 문서를 검색합니다.
    분석에 필요한 시스템, 정책, 특정 문서 정보가 필요할 때 이 도구를 호출하세요.

    Args:
        query (str): 검색할 핵심 질의어, 키워드 또는 전체 문장.
        k (int): 검색할 최대 문서 수 (기본값: 5).
    """
    # [Comment 1 반영] PII 보호: query 원문 대신 길이(비민감 메타데이터)만 로깅
    logger.info(
        "[Tool] search_documents_tool 실행",
        extra={"query_length": len(query), "k": k}
    )
    hybrid_search_service = get_hybrid_search_service()

    try:
        result = await hybrid_search_service.search(query=query, k=k)
        docs = result.results
        if not docs:
            logger.info("[Tool] 검색 결과 없음", extra={"k": k})
            return {"context": "관련된 문서 정보를 찾을 수 없습니다.", "docs": []}

        # JSON-serializable 변환용 리스트
        serialized_docs = []
        formatted_results = []
        
        for i, doc in enumerate(docs, 1):
            safe_doc: SerializedDoc = _normalize_doc(doc)
            serialized_docs.append(safe_doc)

            # 단일 문서 최대 길이 적용
            content = safe_doc["content"]
            content_str = str(content)
            if len(content_str) > _MAX_DOC_CONTENT_CHARS:
                # [Optimization] Pyre2 slice False Positive 방지를 위한 명시적 str 변환 후 조작
                content_str = str(content_str[:_MAX_DOC_CONTENT_CHARS]) + "...(truncated)"  # type: ignore[index]

            # `_normalize_doc` Contract: metadata는 항상 dict (SerializedDoc 타입 보장)
            metadata = safe_doc["metadata"]
            source = metadata.get("source", "unknown")
            formatted_results.append(
                f"--- Document {i} (Source: {source}) ---\n{content_str}"
            )

        final_context = "\n\n".join(formatted_results)
        logger.info(
            "[Tool] 문서 검색 완료",
            extra={"doc_count": len(docs), "total_length": len(final_context)}
        )
        return {"context": final_context, "docs": serialized_docs}

    except Exception as e:
        # [Overall Comment 3 / Comment 2 반영]
        # 상세 예외 내용(str(e))은 로그에만 기록하고, 사용자/LLM에게는 고정 메시지만 반환
        # → 경로·서비스명·인프라 정보 누출 방지
        logger.error(
            "[Tool] 검색 중 오류 발생",
            extra=_build_log_extra(None, error_type=type(e).__name__),
        )
        return {"context": "문서 검색 중 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", "docs": []}


@tool
async def deep_web_search_tool(query: str, k: int = 5) -> dict:
    """
    Tavily API 기반 Deep Web Search 도구입니다.
    기존 내부 문서 검색(RAG)으로 원하는 정보를 찾지 못했거나 부정적인 피드백이 누적되었을 때,
    최신 외부 지식이나 광범위한 웹 문서를 검색하기 위해 이 도구를 호출하세요.

    Args:
        query (str): 검색할 핵심 질의어, 키워드 또는 전체 문장.
        k (int): 검색할 최대 문서 수 (기본값: 5).
    """
    # [Comment 3 반영] 안전한 범위로 k를 검증/제한하여 예기치 않은 부하나 비용 방지
    k = max(1, min(int(k), 10))

    logger.info(
        "[Tool] deep_web_search_tool 실행",
        extra={"query_length": len(query), "k": k}
    )
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.error("[Tool] TAVILY_API_KEY 환경변수가 설정되지 않았습니다.")
        return {"context": "웹 검색 연결 설정이 누락되어 검색할 수 없습니다.", "docs": []}

    try:
        client = _get_tavily_client(api_key)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.search(query=query, search_depth="advanced", max_results=k)
        )

        results = result.get("results", [])
        if not results:
            logger.info("[Tool] 웹 검색 결과 없음", extra={"k": k})
            return {"context": "관련된 웹 검색 결과를 찾을 수 없습니다.", "docs": []}

        formatted_results = []
        serialized_docs = []

        for i, item in enumerate(results, 1):
            content_str = str(item.get("content", ""))
            if len(content_str) > _MAX_DOC_CONTENT_CHARS:
                content_str = str(content_str[:_MAX_DOC_CONTENT_CHARS]) + "...(truncated)"

            source = str(item.get("url", "unknown"))
            formatted_results.append(
                f"--- Web Document {i} (Source: {source}) ---\n{content_str}"
            )

            safe_doc: SerializedDoc = _normalize_doc({
                "id": source,
                "score": float(item.get("score", 0.0) if item.get("score") is not None else 0.0),
                "content": content_str,
                "metadata": {"source": source, "title": item.get("title", "")}
            })
            serialized_docs.append(safe_doc)

        final_context = "\n\n".join(formatted_results)
        logger.info(
            "[Tool] 웹 검색 완료",
            extra={"doc_count": len(results), "total_length": len(final_context)}
        )
        return {"context": final_context, "docs": serialized_docs}

    except Exception as e:
        logger.error(
            "[Tool] 웹 검색 중 오류 발생",
            extra=_build_log_extra(None, error_type=type(e).__name__),
        )
        return {"context": "웹 검색 중 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", "docs": []}

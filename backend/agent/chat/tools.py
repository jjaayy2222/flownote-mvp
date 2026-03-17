# backend/agent/chat/tools.py

import logging
from typing import Any, Dict, List, Optional, TypedDict
from langchain_core.tools import tool  # type: ignore[import, import-untyped, reportMissingImports]
from backend.services.hybrid_search_service import get_hybrid_search_service  # type: ignore[import, import-untyped, reportMissingImports]

logger = logging.getLogger(__name__)

# 도구 내 단일 문서 최대 길이 상수 (하드코딩 방지)
_MAX_DOC_CONTENT_CHARS = 1_000


class SerializedDoc(TypedDict):
    """
    JSON 직렬화 가능한 정규화된 문서 구조.

    [Contract]
    - 모든 필드는 직렬화 가능한 원시 타입만 포함합니다.
    - `metadata` 필드는 항상 `dict` 타입이 보장됩니다.
      호출자는 별도의 isinstance 체크 없이 `safe_doc["metadata"].get(...)` 등을 안전하게 호출할 수 있습니다.
    """
    id: Optional[Any]
    score: Optional[Any]
    content: Any
    metadata: Dict[str, Any]


def _normalize_doc(doc: Any) -> SerializedDoc:
    """
    검색 결과 문서(dict 또는 LangChain Document 유사 객체)를
    JSON 직렬화 가능한 SerializedDoc로 정규화하여 반환합니다.

    [Contract]
    - 반환된 SerializedDoc의 `metadata` 필드는 항상 `dict` 타입입니다. (None 또는 비-dict 입력 시 {} 로 폴백)
    - 호출자는 metadata에 대한 추가 isinstance 검사 없이 안전하게 접근할 수 있습니다.

    Args:
        doc: dict 또는 .page_content / .metadata / .id / .score 속성을 갖는 객체.
    """
    is_dict = isinstance(doc, dict)
    content = (
        doc.get("content", "")
        if is_dict
        else getattr(doc, "page_content", getattr(doc, "content", ""))
    )

    raw_metadata = doc.get("metadata", {}) if is_dict else getattr(doc, "metadata", {})
    metadata: Dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}

    return {
        "id": doc.get("id") if is_dict else getattr(doc, "id", None),
        "score": doc.get("score") if is_dict else getattr(doc, "score", None),
        "content": content,
        "metadata": metadata,
    }


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
            extra={"error_type": type(e).__name__}
        )
        return {"context": "문서 검색 중 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", "docs": []}

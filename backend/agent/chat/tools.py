# backend/agent/chat/tools.py

import logging
from langchain_core.tools import tool
from backend.services.hybrid_search_service import get_hybrid_search_service

logger = logging.getLogger(__name__)

# 도구 내 단일 문서 최대 길이 상수 (하드코딩 방지)
_MAX_DOC_CONTENT_CHARS = 1_000


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

        formatted_results = []
        for i, doc in enumerate(docs, 1):
            content = doc.get("content", "")
            # 단일 문서 최대 길이 적용
            if len(content) > _MAX_DOC_CONTENT_CHARS:
                content = content[:_MAX_DOC_CONTENT_CHARS] + "...(truncated)"

            metadata = doc.get("metadata", {})
            source = metadata.get("source", "unknown")
            formatted_results.append(f"--- Document {i} (Source: {source}) ---\n{content}")

        final_context = "\n\n".join(formatted_results)
        logger.info(
            "[Tool] 문서 검색 완료",
            extra={"doc_count": len(docs), "total_length": len(final_context)}
        )
        return {"context": final_context, "docs": docs}

    except Exception as e:
        # [Overall Comment 3 / Comment 2 반영]
        # 상세 예외 내용(str(e))은 로그에만 기록하고, 사용자/LLM에게는 고정 메시지만 반환
        # → 경로·서비스명·인프라 정보 누출 방지
        logger.error(
            "[Tool] 검색 중 오류 발생",
            extra={"error_type": type(e).__name__}
        )
        return {"context": "문서 검색 중 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", "docs": []}

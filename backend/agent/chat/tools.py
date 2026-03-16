# backend/agent/chat/tools.py

import logging
from langchain_core.tools import tool
from backend.services.hybrid_search_service import get_hybrid_search_service

logger = logging.getLogger(__name__)

@tool
async def search_documents_tool(query: str, k: int = 5) -> str:
    """
    RAG 기반 사내 문서 검색 도구입니다.
    사용자의 질문이나 분석 의도와 관련된 지식 베이스 문서를 검색합니다.
    분석에 필요한 시스템, 정책, 특정 문서 정보가 필요할 때 이 도구를 호출하세요.
    
    Args:
        query (str): 검색할 핵심 질의어, 키워드 또는 전체 문장.
        k (int): 검색할 최대 문서 수 (기본값: 5).
    """
    logger.info(f"[Tool] search_documents_tool 실행: query='{query}'")
    hybrid_search_service = get_hybrid_search_service()
    
    try:
        result = await hybrid_search_service.search(query=query, k=k)
        docs = result.results
        if not docs:
            logger.info("[Tool] 검색 결과 없음")
            return "관련된 문서 정보를 찾을 수 없습니다."
            
        formatted_results = []
        for i, doc in enumerate(docs, 1):
            content = doc.get("content", "")
            if len(content) > 1000:
                content = content[:1000] + "...(truncated)"
                
            metadata = doc.get("metadata", {})
            source = metadata.get("source", "unknown")
            
            formatted_results.append(f"--- Document {i} (Source: {source}) ---\n{content}")
            
        final_context = "\n\n".join(formatted_results)
        logger.info(f"[Tool] {len(docs)}개 문서 검색 완료 (길이: {len(final_context)}자)")
        return final_context
        
    except Exception as e:
        logger.error(f"[Tool] 검색 중 오류 발생: {str(e)}")
        # 안전장치(Fallback): 도구 실행 중 패닉 방지
        return f"문서 검색 중 시스템 오류가 발생했습니다: {str(e)}"

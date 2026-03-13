# tests/unit/services/test_hybrid_search_service.py

import pytest
from unittest.mock import MagicMock
from backend.services.hybrid_search_service import HybridSearchService

@pytest.fixture
def hybrid_search_service():
    # FAISS와 BM25 리트리버를 Mocking하여 순수 로직만 테스트합니다.
    return HybridSearchService(
        faiss_retriever=MagicMock(),
        bm25_retriever=MagicMock()
    )

def test_determine_alpha_semantic_patterns(hybrid_search_service):
    """자연어 질문형 질의에 대해 Semantic Bias (alpha=0.7)가 적용되는지 검증"""
    semantic_queries = [
        "파이썬에서 비동기 프로그래밍을 하는 방법은 무엇인가요?",
        "RAG 시스템의 장단점을 비교해서 설명해줘",
        "이 문서의 핵심 내용을 정리해주겠어?",
        "VectorDB란 무엇인가요?"
    ]
    for query in semantic_queries:
        assert hybrid_search_service.determine_alpha(query) == 0.7

def test_determine_alpha_keyword_patterns(hybrid_search_service):
    """특수 용어, 고유 코드, 날짜가 포함된 질의에 대해 Keyword Bias (alpha=0.3)가 적용되는지 검증"""
    keyword_queries = [
        "2024-03-14 회의록 찾아줘",
        "\"FlowNote\" 프로젝트 계획서",
        "ISS-614 이슈에 대한 내용",
        "버전 v1.2 업데이트 로그"
    ]
    for query in keyword_queries:
        assert hybrid_search_service.determine_alpha(query) == 0.3

def test_determine_alpha_default(hybrid_search_service):
    """특이 패턴이 없는 일반 질의에 대해 기본값(alpha=0.5)이 적용되는지 검증"""
    default_queries = [
        "오늘 날씨 어때?",
        "테스트용 쿼리입니다",
        "Hello world"
    ]
    for query in default_queries:
        assert hybrid_search_service.determine_alpha(query) == 0.5

def test_determine_alpha_empty_input(hybrid_search_service):
    """빈 문자열이나 None에 대해 기본값(alpha=0.5)을 반환하는지 검증"""
    assert hybrid_search_service.determine_alpha("") == 0.5
    assert hybrid_search_service.determine_alpha(None) == 0.5

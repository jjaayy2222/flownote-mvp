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

@pytest.mark.parametrize(
    "query",
    [
        "파이썬에서 비동기 프로그래밍을 하는 방법은 무엇인가요?",
        "RAG 시스템의 장단점을 비교해서 설명해줘",
        "이 문서의 핵심 내용을 정리해주겠어?",
        "VectorDB란 무엇인가요?",
        "이거 알려줄 수 있나요?",
        "그건 무슨 의미인가요?"
    ],
)
def test_determine_alpha_semantic_patterns(hybrid_search_service, query):
    """자연어 질문형 질의에 대해 Semantic Bias (alpha=0.7)가 적용되는지 검증"""
    assert hybrid_search_service.determine_alpha(query) == 0.7

@pytest.mark.parametrize(
    "query",
    [
        "2024-03-14 회의록 찾아줘",
        "\"FlowNote\" 프로젝트 계획서",
        "ISS-614 이슈에 대한 내용",
        "버전 v1.2 업데이트 로그",
        "2023.12.25 데이터",
        "프로젝트 'A' 리포트"
    ],
)
def test_determine_alpha_keyword_patterns(hybrid_search_service, query):
    """특수 용어, 고유 코드, 날짜가 포함된 질의에 대해 Keyword Bias (alpha=0.3)가 적용되는지 검증"""
    assert hybrid_search_service.determine_alpha(query) == 0.3

@pytest.mark.parametrize(
    "query",
    [
        "오늘 날씨 어때?",
        "테스트용 쿼리입니다",
        "Hello world",
        "그냥 검색어"
    ],
)
def test_determine_alpha_default(hybrid_search_service, query):
    """특이 패턴이 없는 일반 질의에 대해 기본값(alpha=0.5)이 적용되는지 검증"""
    assert hybrid_search_service.determine_alpha(query) == 0.5

@pytest.mark.parametrize(
    "query",
    [
        "",
        None,
        "   ",
        "\n\t "
    ],
)
def test_determine_alpha_empty_or_whitespace(hybrid_search_service, query):
    """빈 문자열, None, 공백 문자열에 대해 기본값(alpha=0.5)을 반환하는지 검증"""
    assert hybrid_search_service.determine_alpha(query) == 0.5

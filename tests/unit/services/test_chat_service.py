# tests/unit/services/test_chat_service.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document

from backend.services.chat_service import ChatService
from backend.services.hybrid_search_service import HybridSearchService
from backend.services.onboarding_service import OnboardingService
from backend.services.chat_history_service import ChatHistoryService
from backend.api.models import ChatMessage


@pytest.fixture
def mock_hybrid_search_service():
    return MagicMock(spec=HybridSearchService)


@pytest.fixture
def mock_onboarding_service():
    return MagicMock(spec=OnboardingService)


@pytest.fixture
def mock_chat_history_service():
    return AsyncMock(spec=ChatHistoryService)


@pytest.fixture
def chat_service(mock_hybrid_search_service, mock_onboarding_service, mock_chat_history_service):
    with patch("os.getenv") as mock_getenv:

        def mock_getenv_side_effect(key, default=None):
            env_vars = {
                "RAG_MAX_DOCS": "10",
                "RAG_MAX_DOC_CHARS": "2000",
                "RAG_MAX_TOTAL_CHARS": "16000",
                "GPT4O_MINI_API_KEY": "fake_api_key",
            }
            return env_vars.get(key, default)

        mock_getenv.side_effect = mock_getenv_side_effect

        service = ChatService(
            hybrid_search_service=mock_hybrid_search_service,
            onboarding_service=mock_onboarding_service,
            chat_history_service=mock_chat_history_service,
        )
        return service


# ─────────────────────────────────────────────────────────────
# TEST 1: PII 마스킹 정확도
# ─────────────────────────────────────────────────────────────

def test_mask_pii(chat_service):
    """
    [Phase 1] 안정성 강화: 개인정보(PII) 마스킹 정확도 검증
    """
    original_text = (
        "제 이메일은 test@example.com 이고, "
        "전화번호는 010-1234-5678 입니다. 02-123-4567 도 있습니다."
    )
    masked_text = chat_service._mask_pii(original_text)

    # 이메일 마스킹
    assert "t***@example.com" in masked_text
    assert "test@example.com" not in masked_text

    # 휴대폰 번호 마스킹
    assert "010-****-5678" in masked_text
    assert "010-1234-5678" not in masked_text

    # 유선 번호 마스킹
    assert "02-****-4567" in masked_text
    assert "02-123-4567" not in masked_text

    # None / 빈 문자열 처리
    assert chat_service._mask_pii(None) == ""
    assert chat_service._mask_pii("") == ""


# ─────────────────────────────────────────────────────────────
# TEST 2: 소스 중복 제거 및 페이로드 빌드
# ─────────────────────────────────────────────────────────────

def test_dedupe_and_build_sources(chat_service):
    """
    [Phase 1] 안정성 강화: 소스 중복 제거 및 페이로드 빌드 로직 검증
    """
    docs = [
        Document(page_content="Content 1", metadata={"id": "doc1", "score": 0.9}),
        # 동일한 id → 중복 제거 대상
        Document(page_content="Content 2", metadata={"id": "doc1", "score": 0.8}),
        # 이메일 포함 → PII 마스킹 대상
        Document(
            page_content="Content 3@example.com",
            metadata={"source": "doc2", "id": "doc2", "score": 0.7},
        ),
    ]

    deduped_docs, payload = chat_service._dedupe_and_build_sources(docs)

    # 중복 제거 후 2개만 남아야 함
    assert len(deduped_docs) == 2
    assert len(payload) == 2

    # 구조 검증
    assert payload[0]["id"] == "doc1"
    assert payload[0]["source"] == "doc1"

    assert payload[1]["source"] == "doc2"
    # PII 마스킹 확인: "Content 3@example.com" → "C***ent 3***@example.com" 형태
    # 실제 마스킹 로직은 로컬파트[0] + "***@" + 도메인 이므로 "3***@example.com" 포함 여부 확인
    assert "3***@example.com" in payload[1]["page_content"]


# ─────────────────────────────────────────────────────────────
# TEST 3: 질의 재구성 (Query Rephrasing)
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rephrase_query(chat_service):
    """
    [Phase 1] 안정성 강화: 대화 맥락 기반 질의 재구성 모킹 테스트
    LangChain chain(prompt | llm | StrOutputParser)의 ainvoke를 직접 패치합니다.
    """
    history = [
        ChatMessage(role="user", content="안녕하세요! 맥북 프로에 대해 알려주세요."),
        ChatMessage(role="assistant", content="맥북 프로는 애플의 노트북입니다."),
    ]
    query = "그럼 배터리 타임은 얼마나 가나요?"
    expected = "맥북 프로의 배터리 타임은 얼마나 가나요?"

    # prompt | llm | StrOutputParser() 파이프라인의 실제 실행 경로인
    # RunnableSequence.ainvoke 를 직접 패치합니다.
    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        new_callable=AsyncMock,
        return_value=expected,
    ):
        with patch.object(chat_service, "_get_llm", return_value=MagicMock()):
            result = await chat_service._rephrase_query(query, history)

    assert result == expected


@pytest.mark.asyncio
async def test_rephrase_query_no_history(chat_service):
    """
    [Phase 1] 히스토리가 없으면 원본 쿼리를 그대로 반환하는지 검증 (LLM 호출 없음)
    """
    query = "파이썬에서 비동기 처리 방법은?"
    result = await chat_service._rephrase_query(query, history=[])
    assert result == query

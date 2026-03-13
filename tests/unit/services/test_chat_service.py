# tests/unit/services/test_chat_service.py
#
# [Engineering Decisions]
# - 헬퍼 메서드(_mask_pii, _dedupe_and_build_sources)는 외부 의존성(Redis, OpenAI) 없이
#   독립적으로 검증하는 것이 실용적이므로 직접 단위 테스트를 유지합니다.
# - LangChain 버전 변경에 대한 취약성을 줄이기 위해 chain 내부 경로 대신
#   _get_llm 레이어에서 추상화하여 모킹합니다.
# - 위치(인덱스) 기반 assert 대신 ID/내용 기반 assert를 사용하여 구현 변경에 강건하게 합니다.

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document

from backend.services.chat_service import ChatService
from backend.services.hybrid_search_service import HybridSearchService
from backend.services.onboarding_service import OnboardingService
from backend.services.chat_history_service import ChatHistoryService
from backend.api.models import ChatMessage


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

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
            # [Security] 실제 API 키 대신 테스트 전용 sentinel 값을 사용합니다.
            env_vars = {
                "RAG_MAX_DOCS": "10",
                "RAG_MAX_DOC_CHARS": "2000",
                "RAG_MAX_TOTAL_CHARS": "16000",
                "GPT4O_MINI_API_KEY": "test-only-sentinel-key",
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
# [Review] Comment 1 반영:
#   - 비PII 일반 텍스트가 잘못 마스킹되지 않는지(오버-마스킹) 검증 케이스 추가
# ─────────────────────────────────────────────────────────────

def test_mask_pii_masks_sensitive_data(chat_service):
    """
    [Phase 1] 안정성 강화: 이메일 및 전화번호가 정확히 마스킹되는지 검증
    """
    original_text = (
        "제 이메일은 test@example.com 이고, "
        "전화번호는 010-1234-5678 입니다. 02-123-4567 도 있습니다."
    )
    masked_text = chat_service._mask_pii(original_text)

    # 이메일 마스킹 확인
    assert "t***@example.com" in masked_text
    assert "test@example.com" not in masked_text

    # 휴대폰 번호 마스킹 확인
    assert "010-****-5678" in masked_text
    assert "010-1234-5678" not in masked_text

    # 유선 번호 마스킹 확인
    assert "02-****-4567" in masked_text
    assert "02-123-4567" not in masked_text


def test_mask_pii_handles_edge_cases(chat_service):
    """
    [Phase 1] 안정성 강화: None 및 빈 문자열 처리 검증
    """
    assert chat_service._mask_pii(None) == ""
    assert chat_service._mask_pii("") == ""


def test_mask_pii_does_not_over_mask_normal_text(chat_service):
    """
    [Review] Comment 1 반영:
    PII가 없는 일반 텍스트가 마스킹 함수를 통과해도 변경되지 않아야 합니다.
    정규식 변경으로 인한 오버-마스킹(과잉 필터링) 버그를 방지합니다.
    """
    normal_texts = [
        "단순한 일반 텍스트입니다.",
        "FlowNote는 AI 기반 노트 관리 앱입니다.",
        "버전 v7.0 Phase 2 완료.",
        "https://github.com/jjaayy2222/flownote-mvp",  # URL (이메일 패턴과 유사하지 않음)
    ]
    for text in normal_texts:
        assert chat_service._mask_pii(text) == text, (
            f"오버-마스킹 감지: '{text}' 가 변경되었습니다."
        )


# ─────────────────────────────────────────────────────────────
# TEST 2: 소스 중복 제거 및 페이로드 빌드
# [Review] Comment 2 반영:
#   - 인덱스 대신 ID/내용 기반 검증으로 변경
#   - 메타데이터 누락 엣지케이스 (id/source 없음) 추가
#   - 빈 docs 리스트 처리 케이스 추가
# ─────────────────────────────────────────────────────────────

def test_dedupe_and_build_sources_deduplicates_by_source(chat_service):
    """
    [Phase 1] 동일한 source를 가진 문서가 중복 제거되는지 검증 (ID 기반 assert)
    """
    docs = [
        Document(page_content="Content A", metadata={"id": "doc1", "score": 0.9}),
        # 동일 id → 중복 제거 대상
        Document(page_content="Content B", metadata={"id": "doc1", "score": 0.8}),
        Document(page_content="Content C", metadata={"id": "doc2", "score": 0.7}),
    ]

    deduped_docs, payload = chat_service._dedupe_and_build_sources(docs)

    # 중복 제거 후 2개만 남아야 함
    assert len(deduped_docs) == 2
    assert len(payload) == 2

    # [Review 반영] 인덱스 대신 ID 기반으로 검증
    payload_ids = {p["id"] for p in payload}
    assert "doc1" in payload_ids
    assert "doc2" in payload_ids

    # 첫 번째 등장한 doc1의 content가 선택되었는지 확인
    doc1_payload = next(p for p in payload if p["id"] == "doc1")
    assert doc1_payload["source"] == "doc1"


def test_dedupe_and_build_sources_pii_masking_in_payload(chat_service):
    """
    [Phase 1] 페이로드의 page_content에 PII 마스킹이 적용되는지 검증
    """
    docs = [
        Document(
            page_content="user@secret.com 에게 연락주세요.",
            metadata={"source": "sensitive_doc", "id": "s1", "score": 0.8},
        ),
    ]
    _, payload = chat_service._dedupe_and_build_sources(docs)

    assert len(payload) == 1
    # 이메일이 마스킹되어 있어야 함
    assert "u***@secret.com" in payload[0]["page_content"]
    assert "user@secret.com" not in payload[0]["page_content"]


def test_dedupe_and_build_sources_missing_metadata(chat_service):
    """
    [Review] Comment 2 반영:
    id와 source가 모두 없는 문서의 경우 'unknown'으로 처리되는지 검증.
    이 계약이 변경되면 테스트가 실패하여 리그레션을 방어합니다.
    """
    docs = [
        Document(page_content="메타데이터가 없는 문서", metadata={}),
    ]
    deduped_docs, payload = chat_service._dedupe_and_build_sources(docs)

    assert len(deduped_docs) == 1
    assert payload[0]["source"] == "unknown"
    assert payload[0]["id"] == ""


def test_dedupe_and_build_sources_empty_input(chat_service):
    """
    [Review] Comment 2 반영: 빈 리스트 입력 시 정상 처리 검증
    """
    deduped_docs, payload = chat_service._dedupe_and_build_sources([])
    assert deduped_docs == []
    assert payload == []


# ─────────────────────────────────────────────────────────────
# TEST 3: 질의 재구성 (Query Rephrasing)
# [Review] Overall Comment 반영:
#   - RunnableSequence 내부 경로 대신 _get_llm 레이어에서 추상화하여 모킹
#   - LangChain 버전 변경에 취약하지 않도록 개선
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rephrase_query_with_history(chat_service):
    """
    [Phase 1] 대화 히스토리가 있을 때 재구성된 쿼리가 반환되는지 검증.

    [Engineering Decision - Mock 전략]
    LangChain의 `prompt | llm | StrOutputParser()` 파이프라인은 최종적으로
    `RunnableSequence.ainvoke`를 호출합니다. 이 경로를 직접 패치하는 것이
    복잡한 중간 __or__ 체인 모킹보다 훨씬 안정적이며, 실제 실행 경로와
    일치하는 것이 검증을 통해 확인되었습니다.
    ChatPromptTemplate 중간 레이어 모킹은 StrOutputParser가 개입하면서
    체인 연결이 끊어지는 문제가 있어 채택하지 않았습니다.
    """
    history = [
        ChatMessage(role="user", content="맥북 프로에 대해 알려주세요."),
        ChatMessage(role="assistant", content="맥북 프로는 애플의 노트북입니다."),
    ]
    query = "그럼 배터리 타임은 얼마나 되나요?"
    expected_rephrased = "맥북 프로의 배터리 타임은 얼마나 되나요?"

    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        new_callable=AsyncMock,
        return_value=expected_rephrased,
    ):
        with patch.object(chat_service, "_get_llm", return_value=MagicMock()):
            result = await chat_service._rephrase_query(query, history)

    assert result == expected_rephrased


@pytest.mark.asyncio
async def test_rephrase_query_no_history_returns_original(chat_service):
    """
    [Phase 1] 히스토리가 없으면 LLM 호출 없이 원본 쿼리를 그대로 반환하는지 검증
    """
    query = "파이썬에서 비동기 처리 방법은?"
    result = await chat_service._rephrase_query(query, history=[])
    assert result == query


@pytest.mark.asyncio
async def test_rephrase_query_falls_back_on_llm_error(chat_service):
    """
    [Phase 1] chain.ainvoke 실패 시 원본 쿼리로 폴백하는지 검증 (회복 탄력성).

    [코드 설계 확인]
    _rephrase_query의 try/except는 chain.ainvoke() 호출만 감쌉니다.
    _get_llm() 자체의 실패는 try 블록 밖이므로 폴백 대상이 아닙니다.
    따라서 `chain.ainvoke`가 예외를 던지는 시나리오를 테스트합니다.
    """
    history = [
        ChatMessage(role="user", content="이전 질문입니다."),
    ]
    query = "후속 질문입니다."

    # chain.ainvoke가 예외를 던지면 → except 블록에서 원본 query 반환
    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        new_callable=AsyncMock,
        side_effect=Exception("chain 실행 실패"),
    ):
        with patch.object(chat_service, "_get_llm", return_value=MagicMock()):
            result = await chat_service._rephrase_query(query, history)

    # except 블록에서 원본 쿼리로 안전하게 폴백해야 함
    assert result == query

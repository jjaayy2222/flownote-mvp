# tests/unit/services/test_chat_service.py
#
# [Engineering Decisions]
# 1. _mask_pii, _dedupe_and_build_sources는 외부 의존성(Redis, OpenAI) 없이
#    독립적으로 검증하는 것이 실용적이므로 직접 단위 테스트를 유지합니다.
#    공개 인터페이스를 통한 테스트는 검색 엔진·LLM·Redis를 모두 모킹해야 해서
#    오히려 테스트 신뢰도가 낮아집니다. (pragmatic test boundary 원칙)
#
# 2. _rephrase_query 테스트는 ChatService 자체 메서드인 `_invoke_rephrase_chain`을
#    패치하므로, LangChain 내부 구현(RunnableSequence 경로)에 의존하지 않습니다.
#    이 메서드는 이 목적을 위해 chat_service.py에서 명시적으로 추출되었습니다.
#
# 3. 위치(인덱스) 기반 assert 대신 ID/내용 기반 assert를 사용합니다.

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
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
def chat_service(
    mock_hybrid_search_service, mock_onboarding_service, mock_chat_history_service
):
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

    assert "t***@example.com" in masked_text
    assert "test@example.com" not in masked_text

    assert "010-****-5678" in masked_text
    assert "010-1234-5678" not in masked_text

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
    PII가 없는 일반 텍스트가 마스킹 함수를 통과해도 변경되지 않아야 합니다.
    정규식 변경으로 인한 오버-마스킹(과잉 필터링) 버그를 방지합니다.
    """
    normal_texts = [
        "단순한 일반 텍스트입니다.",
        "FlowNote는 AI 기반 노트 관리 앱입니다.",
        "버전 v7.0 Phase 2 완료.",
        "https://github.com/jjaayy2222/flownote-mvp",
    ]
    for text in normal_texts:
        assert chat_service._mask_pii(text) == text, (
            f"오버-마스킹 감지: '{text}' 가 변경되었습니다."
        )


# ─────────────────────────────────────────────────────────────
# TEST 2: 소스 중복 제거 및 페이로드 빌드
# [Review] Comment 1 반영:
#   - 테스트명과 독스트링이 검증 내용과 일치하도록 수정 (by_id vs by_source 명확화)
#   - source 기준 중복 제거 케이스 별도 추가
# ─────────────────────────────────────────────────────────────

def test_dedupe_and_build_sources_deduplicates_by_id(chat_service):
    """
    [Phase 1] 동일한 ID(key: 'id')를 가진 문서가 중복 제거되는지 검증.

    [Review Comment 1 반영]
    이전 테스트명은 'by_source'였으나 실제로는 'id' 기준 dedup을 검증하고 있었습니다.
    테스트명과 독스트링을 검증 내용과 일치하도록 수정했습니다.
    """
    docs = [
        Document(page_content="Content A", metadata={"id": "doc1", "score": 0.9}),
        # 동일 id → 중복 제거 대상 (source 키는 없으므로 id가 dedup key로 사용됨)
        Document(page_content="Content B", metadata={"id": "doc1", "score": 0.8}),
        Document(page_content="Content C", metadata={"id": "doc2", "score": 0.7}),
    ]

    deduped_docs, payload = chat_service._dedupe_and_build_sources(docs)

    assert len(deduped_docs) == 2
    assert len(payload) == 2

    # ID 기반 검증 (위치 독립적)
    payload_ids = {p["id"] for p in payload}
    assert "doc1" in payload_ids
    assert "doc2" in payload_ids

    # 첫 번째로 등장한 doc1(Content A)이 선택되었는지 확인
    doc1_payload = next(p for p in payload if p["id"] == "doc1")
    assert doc1_payload["source"] == "doc1"


def test_dedupe_and_build_sources_deduplicates_by_source(chat_service):
    """
    [Review Comment 1 반영] source 키를 기준으로 중복 제거가 이루어지는지 검증.

    _dedupe_and_build_sources의 dedup key 우선 순위는 source > id 입니다.
    source 값이 같은 두 문서는 id가 달라도 중복으로 처리됩니다.
    """
    docs = [
        Document(
            page_content="First occurrence",
            metadata={"source": "shared/path.md", "id": "id_a", "score": 0.9},
        ),
        # 동일한 source를 가진 다른 문서 → 중복 제거 대상
        Document(
            page_content="Second occurrence",
            metadata={"source": "shared/path.md", "id": "id_b", "score": 0.7},
        ),
        Document(
            page_content="Unique document",
            metadata={"source": "unique/path.md", "id": "id_c", "score": 0.5},
        ),
    ]

    deduped_docs, payload = chat_service._dedupe_and_build_sources(docs)

    # source가 같으면 중복으로 처리되어 2개만 남아야 함
    assert len(deduped_docs) == 2
    assert len(payload) == 2

    # source 기반 검증
    payload_sources = {p["source"] for p in payload}
    assert "shared/path.md" in payload_sources
    assert "unique/path.md" in payload_sources

    # 첫 번째 등장한 문서(id_a)가 선택되어야 함
    shared_doc = next(p for p in payload if p["source"] == "shared/path.md")
    assert shared_doc["id"] == "id_a"


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
    assert "u***@secret.com" in payload[0]["page_content"]
    assert "user@secret.com" not in payload[0]["page_content"]


def test_dedupe_and_build_sources_missing_metadata(chat_service):
    """
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
    빈 리스트 입력 시 정상 처리 검증
    """
    deduped_docs, payload = chat_service._dedupe_and_build_sources([])
    assert deduped_docs == []
    assert payload == []


# ─────────────────────────────────────────────────────────────
# TEST 3: 질의 재구성 (Query Rephrasing)
# [Review] Overall Comment 1 반영:
#   - `_invoke_rephrase_chain`(ChatService 자체 메서드)을 패치하여
#     LangChain 내부 경로(RunnableSequence) 의존성 완전 제거
# [Review] Comment 2 반영:
#   - history 최근 5개 잘라내기(truncation) 계약 검증 테스트 추가
# ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rephrase_query_with_history(chat_service):
    """
    [Phase 1] 대화 히스토리가 있을 때 재구성된 쿼리가 반환되는지 검증.

    [Engineering Decision - Mock 전략]
    `_invoke_rephrase_chain`은 LangChain 체인 실행을 담당하는 ChatService 자체 메서드입니다.
    이 메서드를 패치하면 LangChain 내부 구현(RunnableSequence 등)에 전혀 의존하지 않으므로
    LangChain 버전 업그레이드에도 테스트가 깨지지 않습니다.
    """
    history = [
        ChatMessage(role="user", content="맥북 프로에 대해 알려주세요."),
        ChatMessage(role="assistant", content="맥북 프로는 애플의 노트북입니다."),
    ]
    query = "그럼 배터리 타임은 얼마나 되나요?"
    expected_rephrased = "맥북 프로의 배터리 타임은 얼마나 되나요?"

    # LangChain 내부가 아닌 ChatService 자체 메서드를 패치합니다.
    with patch.object(
        chat_service,
        "_invoke_rephrase_chain",
        new_callable=AsyncMock,
        return_value=expected_rephrased,
    ):
        result = await chat_service._rephrase_query(query, history)

    assert result == expected_rephrased


@pytest.mark.asyncio
async def test_rephrase_query_no_history_returns_original(chat_service):
    """
    [Phase 1] 히스토리가 없으면 LLM 호출 없이 원본 쿼리를 반환하는지 검증
    """
    query = "파이썬에서 비동기 처리 방법은?"
    result = await chat_service._rephrase_query(query, history=[])
    assert result == query


@pytest.mark.asyncio
async def test_rephrase_query_truncates_history_to_last_five(chat_service):
    """
    [Review] Comment 2 반영:
    _rephrase_query가 전체 history 대신 최근 5개 메시지만 맥락으로 사용하는지 검증.

    chat_service.py의 HISTORY_WINDOW = 5 계약이 실수로 변경되는 것을 방지합니다.
    _invoke_rephrase_chain에 전달된 context_history 인수를 캡쳐하여 검증합니다.
    """
    # 5개를 초과하는 10개의 히스토리 구성
    # [주의] "msg-1"~"msg-9"처럼 부분 문자열 충돌이 없는 고유한 문자열을 사용합니다.
    # 예: "질문 1"은 "질문 10"의 부분 문자열이므로 오탐을 유발할 수 있습니다.
    messages = [f"msg-{chr(ord('A') + i)}" for i in range(10)]  # msg-A ~ msg-J
    history = [
        ChatMessage(role="user", content=msg) for msg in messages
    ]
    query = "최신 질문입니다."

    captured_calls = []

    async def capture_invoke(context_history: str, query: str) -> str:
        captured_calls.append(context_history)
        return "재구성된 쿼리"

    with patch.object(chat_service, "_invoke_rephrase_chain", side_effect=capture_invoke):
        await chat_service._rephrase_query(query, history)

    assert len(captured_calls) == 1, "chain이 정확히 1회 호출되어야 합니다."
    captured_context = captured_calls[0]

    # 최근 5개(msg-F ~ msg-J)만 포함되어야 함
    for msg in messages[-5:]:
        assert msg in captured_context, f"'{msg}'가 context에 포함되어야 합니다."

    # 이전 5개(msg-A ~ msg-E)는 포함되지 않아야 함
    for msg in messages[:5]:
        assert msg not in captured_context, f"'{msg}'는 context에서 제외되어야 합니다."


@pytest.mark.asyncio
async def test_rephrase_query_falls_back_on_invoke_error(chat_service):
    """
    [Phase 1] _invoke_rephrase_chain 실패 시 원본 쿼리로 폴백하는지 검증 (회복 탄력성).

    [코드 설계 확인]
    _rephrase_query의 try/except는 _invoke_rephrase_chain() 호출을 감쌉니다.
    예외 발생 시 경고 로그를 남기고 원본 query를 반환하는 것이 계약입니다.
    """
    history = [
        ChatMessage(role="user", content="이전 질문입니다."),
    ]
    query = "후속 질문입니다."

    with patch.object(
        chat_service,
        "_invoke_rephrase_chain",
        new_callable=AsyncMock,
        side_effect=Exception("chain 실행 실패"),
    ):
        result = await chat_service._rephrase_query(query, history)

    assert result == query

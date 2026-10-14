# tests/unit/test_scheduler_service_unit.py

"""
Unit tests for scheduler_service.py and Golden Dataset ChatHistory join (#12.3.30).
Covers:
- _resolve_qa_context():
  - Exact message_id match with ChatHistory assistant message and preceding user question
  - Fallback to latest assistant message when message_id does not match
  - Graceful fallback to feedback text / default answer when history is empty or Redis unavailable
  - Session caching behavior to prevent N+1 history queries
- extract_and_serialize_golden_dataset():
  - Full batch flow: feedbacks + ChatHistory join + serialization to JSONL
  - Skip flow when no positive feedbacks exist
  - Error resilience and PII masking verification
- Environment parsing and logging security:
  - parse_env_int() boundary, fallback, and type safety
  - _log_env_fallback() sensitive keyword redaction
"""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import backend.services.scheduler_service as ss
from backend.api.models import ChatMessage
from backend.services.golden_dataset_service import FeedbackDataPoint


@pytest.fixture
def mock_feedback():
    """테스트용 단일 FeedbackDataPoint 픽스처"""
    return FeedbackDataPoint(
        session_id="session-xyz-123",
        message_id="msg-assistant-001",
        feedback_text="정말 유익한 답변이었습니다!",
        timestamp="2026-10-14T00:00:00+00:00",
    )


# ============================================================================
# 1. _resolve_qa_context() 단위 테스트
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_qa_context_exact_match(mock_feedback):
    """
    1순위: message_id가 일치하는 assistant 메시지와 그 직전 user 메시지를
    정확히 Q/A로 매칭하여 복원하는지 검증
    """
    history = [
        ChatMessage(role="user", content="플로우노트의 아키텍처는 어떻게 되나요?"),
        ChatMessage(
            role="assistant",
            content="플로우노트는 FastAPI와 Next.js 기반으로 구축되어 있습니다.",
            message_id="msg-assistant-001",
        ),
    ]

    mock_service = MagicMock()
    mock_service.get_history = AsyncMock(return_value=history)

    question, answer, was_joined = await ss._resolve_qa_context(
        mock_feedback, chat_history_service=mock_service
    )

    assert was_joined is True
    assert question == "플로우노트의 아키텍처는 어떻게 되나요?"
    assert answer == "플로우노트는 FastAPI와 Next.js 기반으로 구축되어 있습니다."


@pytest.mark.asyncio
async def test_resolve_qa_context_fallback_latest_assistant(mock_feedback):
    """
    2순위: message_id가 정확히 일치하지 않더라도 세션 내 최신 assistant 메시지와
    직전 user 메시지로 fallback 매칭하는지 검증
    """
    mismatched_fb = FeedbackDataPoint(
        session_id=mock_feedback.session_id,
        message_id="legacy-or-unknown-id",
        feedback_text="피드백 내용",
        timestamp="2026-10-14T00:00:00+00:00",
    )

    history = [
        ChatMessage(role="user", content="이전 질문"),
        ChatMessage(role="assistant", content="이전 답변", message_id="old-id"),
        ChatMessage(role="user", content="최신 질문"),
        ChatMessage(role="assistant", content="최신 답변", message_id="recent-id"),
    ]

    mock_service = MagicMock()
    mock_service.get_history = AsyncMock(return_value=history)

    question, answer, was_joined = await ss._resolve_qa_context(
        mismatched_fb, chat_history_service=mock_service
    )

    assert was_joined is True
    assert question == "최신 질문"
    assert answer == "최신 답변"


@pytest.mark.asyncio
async def test_resolve_qa_context_empty_history_fallback(mock_feedback):
    """
    대화 히스토리가 비어있거나 Redis 조회가 실패할 때, 예외를 던지지 않고
    기본 피드백 텍스트 기반으로 안전하게 fallback하는지 검증
    """
    mock_service = MagicMock()
    mock_service.get_history = AsyncMock(return_value=[])

    question, answer, was_joined = await ss._resolve_qa_context(
        mock_feedback, chat_history_service=mock_service
    )

    assert was_joined is False
    assert question == f"Feedback: {mock_feedback.feedback_text}"
    assert answer == ss._FALLBACK_ANSWER_TEXT


@pytest.mark.asyncio
async def test_resolve_qa_context_service_error_fallback(mock_feedback):
    """
    chat_history_service에서 예외 발생 시 안전하게 fallback 처리
    """
    mock_service = MagicMock()
    mock_service.get_history = AsyncMock(
        side_effect=RuntimeError("Redis connection failed")
    )

    question, answer, was_joined = await ss._resolve_qa_context(
        mock_feedback, chat_history_service=mock_service
    )

    assert was_joined is False
    assert question == f"Feedback: {mock_feedback.feedback_text}"
    assert answer == ss._FALLBACK_ANSWER_TEXT


@pytest.mark.asyncio
async def test_resolve_qa_context_session_cache_prevents_duplicate_calls(mock_feedback):
    """
    동일 세션에 대해 session_cache가 제공되면 get_history()를 중복 호출하지 않는지 검증
    """
    history = [
        ChatMessage(role="user", content="질문 1"),
        ChatMessage(role="assistant", content="답변 1", message_id="msg-assistant-001"),
    ]

    mock_service = MagicMock()
    mock_service.get_history = AsyncMock(return_value=history)

    session_cache = {}

    # 첫 번째 호출: get_history 1회 호출
    q1, a1, j1 = await ss._resolve_qa_context(
        mock_feedback, chat_history_service=mock_service, session_cache=session_cache
    )
    assert j1 is True
    assert mock_service.get_history.call_count == 1

    # 두 번째 호출 (동일 세션): 캐시에서 조회하므로 추가 호출 없음
    q2, a2, j2 = await ss._resolve_qa_context(
        mock_feedback, chat_history_service=mock_service, session_cache=session_cache
    )
    assert j2 is True
    assert mock_service.get_history.call_count == 1


# ============================================================================
# 2. extract_and_serialize_golden_dataset() 배치 흐름 검증
# ============================================================================


@pytest.mark.asyncio
async def test_extract_and_serialize_golden_dataset_success(
    tmp_path, monkeypatch, caplog
):
    """
    피드백 수집 → ChatHistory 조인 → OpenAI Fine-tuning 포맷 변환 → JSONL 파일 저장
    전체 파이프라인의 정상 동작 및 PII 마스킹 검증
    """
    out_dir = tmp_path / "golden_dataset"
    monkeypatch.setattr(ss, "GOLDEN_DATASET_DIR", out_dir)

    feedbacks = [
        FeedbackDataPoint(
            session_id="session-user-1",
            message_id="msg-1",
            feedback_text="좋은 답변",
            timestamp="2026-10-14T00:00:00+00:00",
        ),
        FeedbackDataPoint(
            session_id="session-user-2",
            message_id="msg-2",
            feedback_text=None,
            timestamp="2026-10-14T00:00:00+00:00",
        ),
    ]

    history_1 = [
        ChatMessage(role="user", content="FastAPI 장점은?"),
        ChatMessage(
            role="assistant",
            content="비동기 지원과 빠른 속도입니다.",
            message_id="msg-1",
        ),
    ]

    mock_history_service = MagicMock()

    async def mock_get_history(session_id, limit=50):
        if session_id == "session-user-1":
            return history_1
        return []  # session-user-2는 히스토리 없음 (fallback)

    mock_history_service.get_history = AsyncMock(side_effect=mock_get_history)
    monkeypatch.setattr(ss, "get_chat_history_service", lambda: mock_history_service)

    with patch(
        "backend.services.scheduler_service.filter_positive_feedbacks",
        AsyncMock(return_value=feedbacks),
    ), caplog.at_level(logging.INFO):
        await ss.extract_and_serialize_golden_dataset()

    # jsonl 파일 생성 확인
    jsonl_files = list(out_dir.glob("*.jsonl"))
    assert len(jsonl_files) == 1

    lines = [
        json.loads(line)
        for line in jsonl_files[0].read_text(encoding="utf-8").splitlines()
    ]
    assert len(lines) == 2

    # 1번째 라인: 조인 성공
    item1 = lines[0]
    messages1 = item1["messages"]
    assert messages1[0]["role"] == "system"
    assert messages1[1]["content"] == "FastAPI 장점은?"
    assert messages1[2]["content"] == "비동기 지원과 빠른 속도입니다."
    # PII 마스킹 확인 (session_id가 원문 그대로 노출되지 않고 마스킹됨)
    assert item1["session_id"] != "session-user-1"
    assert "session-user-1" not in item1["session_id"]

    # 2번째 라인: fallback 처리
    item2 = lines[1]
    messages2 = item2["messages"]
    assert messages2[1]["content"] == "Feedback: No text"
    assert messages2[2]["content"] == ss._FALLBACK_ANSWER_TEXT

    # 요약 로그 확인
    summary_logs = [
        r
        for r in caplog.records
        if "Daily golden dataset extraction completed" in r.getMessage()
    ]
    assert len(summary_logs) == 1
    assert getattr(summary_logs[0], "joined_count", 0) == 1
    assert getattr(summary_logs[0], "fallback_count", 0) == 1


@pytest.mark.asyncio
async def test_extract_and_serialize_golden_dataset_no_feedbacks(
    tmp_path, monkeypatch, caplog
):
    """피드백이 없는 날은 파일 생성을 건너뛰고 스킵 로그를 남김"""
    out_dir = tmp_path / "golden_dataset"
    monkeypatch.setattr(ss, "GOLDEN_DATASET_DIR", out_dir)

    with patch(
        "backend.services.scheduler_service.filter_positive_feedbacks",
        AsyncMock(return_value=[]),
    ), caplog.at_level(logging.INFO):
        await ss.extract_and_serialize_golden_dataset()

    # 파일이 생성되지 않아야 함
    assert not out_dir.exists() or len(list(out_dir.glob("*.jsonl"))) == 0
    assert any(
        "No positive feedbacks found today" in r.getMessage() for r in caplog.records
    )


# ============================================================================
# 3. 환경 변수 파싱 및 보안 검증
# ============================================================================


def test_parse_env_int_boundaries_and_types(monkeypatch):
    """parse_env_int의 기본값, 범위 검증 및 타입 안전성 테스트"""
    # 설정되지 않은 키 -> default
    assert ss.parse_env_int("NON_EXISTENT_VAR", 5, 0, 10) == 5

    # 공백 키 -> default
    monkeypatch.setenv("TEST_EMPTY_VAR", "   ")
    assert ss.parse_env_int("TEST_EMPTY_VAR", 5, 0, 10) == 5

    # 정상 범위
    monkeypatch.setenv("TEST_VALID_VAR", "7")
    assert ss.parse_env_int("TEST_VALID_VAR", 5, 0, 10) == 7

    # 범위 초과 -> default
    monkeypatch.setenv("TEST_OVER_VAR", "15")
    assert ss.parse_env_int("TEST_OVER_VAR", 5, 0, 10) == 5

    # 문자열 -> default
    monkeypatch.setenv("TEST_NAN_VAR", "abc")
    assert ss.parse_env_int("TEST_NAN_VAR", 5, 0, 10) == 5


def test_log_env_fallback_redaction(caplog):
    """민감 키워드(KEY, SECRET, TOKEN 등)가 포함된 환경 변수는 로그에서 REDACTED 처리되는지 검증"""
    with caplog.at_level(logging.WARNING):
        ss._log_env_fallback(
            "OPENAI_API_KEY", "is invalid", "default_val", raw_val="sk-12345secret"
        )

    warning_msgs = [r.getMessage() for r in caplog.records]
    assert len(warning_msgs) == 1
    # 민감한 시크릿 값이 노출되지 않고 마스킹되었는지 검증
    assert "sk-12345secret" not in warning_msgs[0]
    assert "***REDACTED***" in warning_msgs[0]

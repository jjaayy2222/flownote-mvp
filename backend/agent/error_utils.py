# backend/agent/error_utils.py
"""
[KO] AI 에이전트 모듈 공용 PII-안전 에러 로깅 헬퍼.

이 모듈은 플래너, 리스폰더, 도구, 그래프 라우터 등 에이전트 경계 레이어(boundary layer)에서
발생하는 예외를 PII 노출 없이 구조화된 포맷으로 로깅하기 위한 공통 유틸리티를 제공합니다.

설계 원칙:
  - 이 모듈은 다른 agent 하위 모듈을 import하지 않아 순환 의존성을 완전히 차단합니다.
  - 민감 정보(PII)는 절대 로그에 원문으로 남기지 않습니다.
  - 에러 메시지 잘라내기(truncation) 및 보안 메타데이터는 이 모듈에서 단일 관리합니다.

[EN] Shared PII-safe error logging helper for AI agent modules.

Provides a unified structured logging pattern for exceptions at the boundary layer
(planner, responder, tools, graph traversal) without leaking PII.

Design Principles:
  - No imports from other agent sub-modules (prevents circular dependencies).
  - PII is never logged in plain text.
  - Truncation strategy and security metadata are centrally managed here.
"""

import logging
import re
from itertools import islice
from typing import Any, Dict, Optional

# ─────────────────────────────────────────────────────────────────────────────
# 모듈 상수 (하드코딩 완전 배제)
# ─────────────────────────────────────────────────────────────────────────────

# [Security] 로그에 포함될 에러 메시지의 최대 길이 제한 (PII 노출 면적 최소화)
_MAX_ERROR_MSG_CHARS: int = 200

# [Security] PII 마스킹 정규식 (프리컴파일로 성능 최적화)
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TOKEN_PATTERN = re.compile(r"\b[0-9A-Za-z]{32,}\b")
_E164_MAX_DIGITS: int = 15
_PHONE_PATTERN = re.compile(
    rf"""
    (?<!\d)
    (?!(?:\D?\d){{{_E164_MAX_DIGITS + 1},}}(?!\d))
    (?:\+?\d{{1,3}}[- .]?)?
    \(?0?\d{{1,4}}\)?
    [- .]?\d{{3,5}}
    [- .]?\d{{4}}
    (?!\d)
    """,
    re.VERBOSE,
)

# [Security] 로그 내 보안 정책 식별자 — 변경 시 이 상수 하나만 수정하면 모든 호출부에 반영됨
_SECURITY_NOTICE: str = (
    "Traceback omitted for PII protection; error_msg sanitized and truncated"
)

# log_agent_error()에서 허용하는 로그 레벨 집합
_SUPPORTED_LOG_LEVELS: frozenset = frozenset({"error", "warning", "critical"})


def _sanitize_pii(text: str) -> str:
    """
    [KO] 텍스트 내의 이메일, 전화번호, 인증 토큰 등 민감 정보(PII)를 탐지하여 마스킹합니다.
    [EN] Detects and masks PII (email, phone number, auth tokens) in the given text.
    """
    sanitized = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    sanitized = _PHONE_PATTERN.sub("[REDACTED_PHONE]", sanitized)
    sanitized = _TOKEN_PATTERN.sub("[REDACTED_TOKEN]", sanitized)
    return sanitized


def sanitize_error_msg(
    exc: BaseException, max_chars: int = _MAX_ERROR_MSG_CHARS
) -> str:
    """
    [KO] 예외 객체의 문자열 표현을 PII 마스킹 처리 후 최대 길이로 잘라 반환합니다.

    [EN] Returns a PII-sanitized and length-truncated string representation of the exception.

    Args:
        exc: 처리된 예외 객체 / The caught exception.
        max_chars: 반환 문자열의 최대 길이 (기본값: 모듈 상수 _MAX_ERROR_MSG_CHARS).
                   / Maximum length of the returned string.

    Returns:
        마스킹·잘라내기 처리된 안전한 에러 메시지 문자열.
        / A safe, masked, truncated error message string.
    """
    sanitized = _sanitize_pii(str(exc))
    # Pyre2 String Slicing 오판단 우회를 위해 islice 사용
    return "".join(islice(sanitized, max_chars))


def log_agent_error(
    logger_instance: logging.Logger,
    context_label: str,
    exc: BaseException,
    extra_metadata: Optional[Dict[str, Any]] = None,
    *,
    level: str = "error",
) -> None:
    """
    [KO] 에이전트 경계 레이어에서 발생한 예외를 PII-안전하게 구조화된 포맷으로 로깅합니다.

    모든 호출부에서 동일한 truncation 방식과 보안 메타데이터 키를 사용하도록 강제하여
    추후 정책 변경 시 이 함수 하나만 수정하면 모든 위치에 반영됩니다.

    [EN] Logs an agent boundary exception in a PII-safe, structured format.

    Centralizes truncation strategy and security metadata so that policy changes
    only require updating this single function.

    Args:
        logger_instance: 호출 모듈의 module-level logger 인스턴스.
                         / The module-level logger of the calling module.
        context_label:  발생 위치와 상황을 설명하는 레이블.
                        (예: "[Planner] LLM 네트워크 에러 발생")
                        / Human-readable label identifying the error context.
        exc:            처리할 예외 객체 / The caught exception to log.
        extra_metadata: 추가적인 비민감 메타데이터 딕셔너리.
                        (예: {"action": "graph_traversal", "tool": "search_documents_tool"})
                        / Additional non-sensitive metadata dict to include in the log.
        level:          로그 레벨 문자열. "error" | "warning" | "critical" (기본값: "error").
                        / Log level string. Must be one of the supported levels.

    Raises:
        ValueError: level 파라미터가 지원되지 않는 값인 경우.
                    / If `level` is not in the set of supported log levels.
    """
    if level not in _SUPPORTED_LOG_LEVELS:
        raise ValueError(
            f"Unsupported log level '{level}'. Must be one of: {sorted(_SUPPORTED_LOG_LEVELS)}"
        )

    # 보안 키를 기본으로 구성하고, 호출부의 extra_metadata는 앞에 붙여 보안 키가 덮어써지지 않게 함
    extra: Dict[str, Any] = {
        "error_type": type(exc).__name__,
        "error_msg": sanitize_error_msg(exc),
        "security": _SECURITY_NOTICE,
    }
    if extra_metadata:
        extra = {**extra_metadata, **extra}

    log_fn = getattr(logger_instance, level)
    log_fn(context_label, extra=extra)

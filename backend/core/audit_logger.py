# backend/core/audit_logger.py

"""
GDPR Audit Logger — v9.0 Phase 2-4 (Privacy & Compliance)
==========================================================

감사 로그(Audit Log) 인프라 모듈.

[설계 원칙]
  - PII 마스킹 원칙: 로그에 user_id 원문은 절대 기록하지 않으며, 항상 masked_uid로만 식별.
  - [OBS] 태그 준수: 관측성(Observability) 목적의 모든 로그는 [OBS] 접두어를 사용.
  - 백엔드 외부화: 로그 저장소 백엔드(file / db / cloudwatch)를 AUDIT_LOG_BACKEND 환경 변수로 제어.
  - 보관 정책: 90일 보관 후 자동 영구 삭제 (트리거 인터페이스만 제공, 실제 실행은 스케줄러에 위임).
  - 하드코딩 금지: 모든 상수는 환경 변수 또는 모듈 레벨 상수로 외부화.

[수명 주기]
  - FastAPI lifespan 또는 Celery 훅에서 schedule_audit_log_cleanup()을 등록하여 보관 정책을 강제.

[주요 참조처 (Consumers)]
  - backend.services.privacy_service: 삭제·익명화 처리 결과 기록
  - 향후 추가되는 GDPR 처리 파이프라인 전체
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# =============================================================================
# 모듈 레벨 상수 (환경 변수 우선, 미설정 시 안전한 기본값)
# =============================================================================

# 감사 로그 저장소 백엔드 (유효값: "file" / "db" / "cloudwatch")
_AUDIT_LOG_BACKEND_ENV_KEY = "AUDIT_LOG_BACKEND"
_VALID_BACKENDS = frozenset({"file", "db", "cloudwatch"})
_DEFAULT_BACKEND = "file"

_raw_backend = os.getenv(_AUDIT_LOG_BACKEND_ENV_KEY, "").strip().lower()
AUDIT_LOG_BACKEND: str = _raw_backend if _raw_backend in _VALID_BACKENDS else _DEFAULT_BACKEND

if _raw_backend and _raw_backend not in _VALID_BACKENDS:
    logger.warning(
        "[OBS][AUDIT][CONFIG] '%s'=%r is not a valid backend (valid: %s). "
        "Falling back to default '%s'.",
        _AUDIT_LOG_BACKEND_ENV_KEY,
        _raw_backend,
        sorted(_VALID_BACKENDS),
        _DEFAULT_BACKEND,
    )

# 감사 로그 파일 저장 경로 (file 백엔드 사용 시)
_AUDIT_LOG_FILE_PATH_ENV_KEY = "AUDIT_LOG_FILE_PATH"
_DEFAULT_AUDIT_LOG_FILE_PATH = "logs/audit.log"
AUDIT_LOG_FILE_PATH: str = (
    os.getenv(_AUDIT_LOG_FILE_PATH_ENV_KEY, "").strip()
    or _DEFAULT_AUDIT_LOG_FILE_PATH
)

# 감사 로그 보관 일수
_AUDIT_LOG_RETENTION_DAYS_ENV_KEY = "AUDIT_LOG_RETENTION_DAYS"
_DEFAULT_AUDIT_LOG_RETENTION_DAYS = 90
_MIN_RETENTION_DAYS = 1
_MAX_RETENTION_DAYS = 3650  # 10년 상한

_raw_retention = os.getenv(_AUDIT_LOG_RETENTION_DAYS_ENV_KEY)
try:
    _parsed_retention = int(_raw_retention) if _raw_retention is not None else _DEFAULT_AUDIT_LOG_RETENTION_DAYS
    if not (_MIN_RETENTION_DAYS <= _parsed_retention <= _MAX_RETENTION_DAYS):
        logger.warning(
            "[OBS][AUDIT][CONFIG] '%s'=%d is outside safe range [%d, %d]. "
            "Falling back to default %d days.",
            _AUDIT_LOG_RETENTION_DAYS_ENV_KEY,
            _parsed_retention,
            _MIN_RETENTION_DAYS,
            _MAX_RETENTION_DAYS,
            _DEFAULT_AUDIT_LOG_RETENTION_DAYS,
        )
        _parsed_retention = _DEFAULT_AUDIT_LOG_RETENTION_DAYS
except (ValueError, TypeError):
    logger.warning(
        "[OBS][AUDIT][CONFIG] '%s'=%r is not a valid integer. "
        "Falling back to default %d days.",
        _AUDIT_LOG_RETENTION_DAYS_ENV_KEY,
        _raw_retention,
        _DEFAULT_AUDIT_LOG_RETENTION_DAYS,
    )
    _parsed_retention = _DEFAULT_AUDIT_LOG_RETENTION_DAYS

AUDIT_LOG_RETENTION_DAYS: int = _parsed_retention

# PII 마스킹 접두어 길이 (masked_uid 노출 자릿수)
_MASKED_UID_PREFIX_LEN_ENV_KEY = "MASKED_UID_PREFIX_LEN"
_DEFAULT_MASKED_UID_PREFIX_LEN = 8
_MIN_MASKED_UID_PREFIX_LEN = 4
_MAX_MASKED_UID_PREFIX_LEN = 16

_raw_prefix_len = os.getenv(_MASKED_UID_PREFIX_LEN_ENV_KEY)
try:
    _parsed_prefix_len = (
        int(_raw_prefix_len) if _raw_prefix_len is not None else _DEFAULT_MASKED_UID_PREFIX_LEN
    )
    if not (_MIN_MASKED_UID_PREFIX_LEN <= _parsed_prefix_len <= _MAX_MASKED_UID_PREFIX_LEN):
        logger.warning(
            "[OBS][AUDIT][CONFIG] '%s'=%d is outside safe range [%d, %d]. "
            "Falling back to default %d.",
            _MASKED_UID_PREFIX_LEN_ENV_KEY,
            _parsed_prefix_len,
            _MIN_MASKED_UID_PREFIX_LEN,
            _MAX_MASKED_UID_PREFIX_LEN,
            _DEFAULT_MASKED_UID_PREFIX_LEN,
        )
        _parsed_prefix_len = _DEFAULT_MASKED_UID_PREFIX_LEN
except (ValueError, TypeError):
    logger.warning(
        "[OBS][AUDIT][CONFIG] '%s'=%r is not a valid integer. "
        "Falling back to default %d.",
        _MASKED_UID_PREFIX_LEN_ENV_KEY,
        _raw_prefix_len,
        _DEFAULT_MASKED_UID_PREFIX_LEN,
    )
    _parsed_prefix_len = _DEFAULT_MASKED_UID_PREFIX_LEN

MASKED_UID_PREFIX_LEN: int = _parsed_prefix_len


# =============================================================================
# 감사 이벤트 타입
# =============================================================================

class AuditEventType(str, Enum):
    """
    감사 로그에 기록되는 이벤트 유형.
    향후 이벤트 추가 시 이 Enum에만 정의하여 하드코딩 방지.
    """
    DATA_DELETE_REQUESTED = "DATA_DELETE_REQUESTED"
    DATA_DELETE_SUCCESS = "DATA_DELETE_SUCCESS"
    DATA_DELETE_FAILURE = "DATA_DELETE_FAILURE"
    DATA_ANONYMIZE_SUCCESS = "DATA_ANONYMIZE_SUCCESS"
    DATA_ANONYMIZE_FAILURE = "DATA_ANONYMIZE_FAILURE"
    AUDIT_LOG_CLEANUP = "AUDIT_LOG_CLEANUP"
    ACCESS_AUDIT_LOG = "ACCESS_AUDIT_LOG"


# =============================================================================
# PII 마스킹 헬퍼
# =============================================================================

def mask_uid(hashed_user_id: str) -> str:
    """
    hashed_user_id의 앞 N자리만 노출하고 나머지를 '*'로 마스킹합니다.

    [보안 원칙]
      - 로그 및 관측 시스템에서 user_id 원문은 절대 사용하지 않습니다.
      - hashed_user_id조차도 일부만 노출하여 재식별 리스크를 최소화합니다.
      - 노출 길이는 MASKED_UID_PREFIX_LEN (환경 변수) 으로 제어합니다.

    Args:
        hashed_user_id: SHA-256 등으로 해싱된 사용자 식별자 (원문 user_id 금지).

    Returns:
        앞 N자리 + '****' 형태의 마스킹된 문자열.
    """
    if not hashed_user_id:
        return "****"
    prefix = hashed_user_id[:MASKED_UID_PREFIX_LEN]
    return f"{prefix}****"


# =============================================================================
# 구조화 감사 로그 포맷터
# =============================================================================

def _build_audit_record(
    event_type: AuditEventType,
    masked_uid: str,
    result: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    감사 로그 레코드를 구조화된 딕셔너리로 생성합니다.

    Args:
        event_type: 이벤트 유형 (AuditEventType).
        masked_uid: 마스킹된 사용자 식별자 (mask_uid() 출력값).
        result: 처리 결과 요약 문자열 (예: "success", "failure: <reason>").
        extra: 추가 컨텍스트 정보 (PII 미포함 원칙 준수 필수).

    Returns:
        감사 로그 레코드 딕셔너리.
    """
    record: dict[str, Any] = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "event_type": event_type.value,
        "masked_uid": masked_uid,
        "result": result,
    }
    if extra:
        record["extra"] = extra
    return record


def write_audit_log(
    event_type: AuditEventType,
    masked_uid: str,
    result: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    감사 이벤트를 설정된 백엔드에 기록합니다.

    [백엔드 라우팅]
      - "file":        AUDIT_LOG_FILE_PATH 경로의 파일에 JSON Lines 형식으로 기록.
      - "db":          DB 연동은 향후 구현 예정 (현재 INFO 로그로 대체).
      - "cloudwatch":  CloudWatch Logs 연동은 향후 구현 예정 (현재 INFO 로그로 대체).

    Args:
        event_type: 감사 이벤트 유형.
        masked_uid:  마스킹된 사용자 식별자.
        result:      처리 결과 요약.
        extra:       추가 컨텍스트 (PII 금지).
    """
    record = _build_audit_record(event_type, masked_uid, result, extra)

    if AUDIT_LOG_BACKEND == "file":
        _write_to_file(record)
    elif AUDIT_LOG_BACKEND in ("db", "cloudwatch"):
        # 향후 구현 예정: 현재는 표준 로거로 대체하여 관측성 유지
        logger.info(
            "[OBS][AUDIT] event_type=%s masked_uid=%s result=%s backend=%s (not yet implemented)",
            event_type.value,
            masked_uid,
            result,
            AUDIT_LOG_BACKEND,
        )
    else:
        # 방어적 처리: 유효하지 않은 백엔드는 모듈 로딩 시 이미 경고되므로 여기서는 로거만 사용
        logger.warning(
            "[OBS][AUDIT] Unknown backend '%s'. Falling back to logger output.",
            AUDIT_LOG_BACKEND,
        )
        logger.info("[OBS][AUDIT] %s", json.dumps(record, ensure_ascii=False))


def _write_to_file(record: dict[str, Any]) -> None:
    """
    감사 로그 레코드를 파일에 JSON Lines 형식으로 기록합니다.
    디렉토리가 없을 경우 자동 생성합니다.
    """
    try:
        log_path = AUDIT_LOG_FILE_PATH
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        # 파일 I/O 실패 시 표준 로거로 폴백 (관측성 유지, 프로세스 중단 방지)
        logger.error(
            "[OBS][AUDIT] Failed to write audit log to file '%s': %s. "
            "Falling back to logger output. record=%s",
            AUDIT_LOG_FILE_PATH,
            type(e).__name__,
            json.dumps(record, ensure_ascii=False),
        )


# =============================================================================
# 감사 로그 보관 정책 — 스케줄러 트리거 인터페이스
# =============================================================================

def get_audit_log_cutoff_datetime() -> datetime:
    """
    현재 시각을 기준으로 감사 로그 보관 만료 기준 시각을 반환합니다.
    AUDIT_LOG_RETENTION_DAYS (환경 변수) 일 이전의 레코드는 삭제 대상입니다.

    Returns:
        보관 만료 기준 datetime (UTC).
    """
    return datetime.now(tz=timezone.utc) - timedelta(days=AUDIT_LOG_RETENTION_DAYS)


def schedule_audit_log_cleanup() -> None:
    """
    감사 로그 자동 영구 삭제 스케줄러의 트리거 인터페이스입니다.

    [수명 주기 가이드라인]
    - FastAPI lifespan 컨텍스트 매니저: yield 이전 블록에서 호출하여 스케줄러 등록.
    - Celery Beat: periodic task로 등록하여 주기적 실행 보장.
    - 실제 파일/DB/CloudWatch 레코드 삭제 로직은 각 백엔드 구현체에서 get_audit_log_cutoff_datetime()을 참조하여 수행.

    현재는 트리거 의도를 INFO 로그로 기록하며, 실제 삭제 구현은 각 백엔드 통합 단계에서 완성합니다.
    """
    cutoff = get_audit_log_cutoff_datetime()
    logger.info(
        "[OBS][AUDIT] Audit log cleanup scheduled. "
        "Records older than %s (retention=%d days) will be purged. backend=%s",
        cutoff.isoformat(),
        AUDIT_LOG_RETENTION_DAYS,
        AUDIT_LOG_BACKEND,
    )
    write_audit_log(
        event_type=AuditEventType.AUDIT_LOG_CLEANUP,
        masked_uid="system",
        result=f"cleanup_triggered: cutoff={cutoff.isoformat()}",
        extra={"retention_days": AUDIT_LOG_RETENTION_DAYS, "backend": AUDIT_LOG_BACKEND},
    )

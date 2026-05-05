# backend/api/endpoints/privacy.py

"""
GDPR Right-to-Erasure API Endpoint — v9.0 Phase 2-4 (Integration & Compliance)
=================================================================================

[역할]
  - 사용자 삭제 요청(Right to Erasure, GDPR 제17조)의 단일 API 진입점.
  - 2단계(Vector Data 삭제) → 3단계(Interaction Log 익명화) → 1단계(감사 로그 기록)
    순서를 오케스트레이션합니다.

[보안 설계]
  - hashed_user_id는 SHA-256 결과인 64자리 hex 고정 포맷을 Pydantic에서 강제 검증합니다.
    user_id 원문은 이 레이어에 절대 진입하지 않습니다.
  - log_fields_to_anonymize 각 항목은 최대 길이 및 허용 문자 패턴을 검증합니다.
  - PII가 포함될 수 있는 예외 메시지(str(exception))는 로그에 기록하지 않으며,
    예외 타입명만 기록합니다.
  - 모든 처리 결과는 audit_logger를 통해 감사 로그에 기록됩니다.
  - 인증 의존성(get_current_user)은 기존 deps.py 패턴을 재사용합니다.

[응답 스키마]
  - anonymization_results: list[AnonymizationSummary] — 성공/실패 모두 동일한 스키마.
    field_index: 요청 순서 인덱스 (0-based) — PII 없이 원본 필드와 매핑 가능.

[Graceful Degradation 정책]
  - `delete_user_data()` 내부 예외 → 파이프라인 전체 중단, 500 반환 + FAILURE 감사 로그
  - 익명화 실패 → 해당 필드만 실패 처리, 전체 파이프라인 유지
  - 감사 로그 기록 실패 → `audit_logged=False`로 응답에 정확히 반영, 프로세스 중단 없음

[환경 변수 의존성]
  - AUDIT_LOG_BACKEND, PBKDF2_ITERATIONS 등 — privacy_service.py / audit_logger.py 참조
"""

from __future__ import annotations

import functools
import hashlib
import logging
import os
import re
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from backend.api.deps import get_current_user
from backend.core.audit_logger import AuditConfigError, AuditEventType, mask_uid, write_audit_log
from backend.services.privacy_service import (
    AnonymizationResult,
    DeletionResult,
    anonymize_log_entry,
    delete_user_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/privacy", tags=["privacy"])

# SHA-256 결과: 64자리 16진수 (대소문자 허용)
_SHA256_HEX_PATTERN: re.Pattern[str] = re.compile(r"^[0-9a-fA-F]{64}$")

# log_fields_to_anonymize 항목별 제한 (하드코딩 금지 — 환경 변수 우선)
_LOG_FIELD_MAX_LENGTH_ENV_KEY = "PRIVACY_LOG_FIELD_MAX_LENGTH"
_DEFAULT_LOG_FIELD_MAX_LENGTH = 4096
_MIN_LOG_FIELD_MAX_LENGTH = 64
_MAX_LOG_FIELD_MAX_LENGTH = 1_048_576  # 1 MiB 상한


@functools.lru_cache(maxsize=None)
def _get_log_field_max_length() -> int:
    """PRIVACY_LOG_FIELD_MAX_LENGTH 환경 변수를 파싱하여 반환합니다 (범위 검증 및 캐싱 포함)."""
    raw = os.getenv(_LOG_FIELD_MAX_LENGTH_ENV_KEY)
    default = _DEFAULT_LOG_FIELD_MAX_LENGTH
    if raw is None:
        return default
    try:
        value = int(raw)
        if not (_MIN_LOG_FIELD_MAX_LENGTH <= value <= _MAX_LOG_FIELD_MAX_LENGTH):
            logger.warning(
                "[OBS][PRIVACY][CONFIG] '%s'=%d is outside range [%d, %d]. Falling back to %d.",
                _LOG_FIELD_MAX_LENGTH_ENV_KEY, value,
                _MIN_LOG_FIELD_MAX_LENGTH, _MAX_LOG_FIELD_MAX_LENGTH, default,
            )
            return default
        return value
    except (ValueError, TypeError):
        logger.warning(
            "[OBS][PRIVACY][CONFIG] '%s'=%r is not a valid integer. Falling back to %d.",
            _LOG_FIELD_MAX_LENGTH_ENV_KEY, raw, default,
        )
        return default


# =============================================================================
# 요청/응답 모델
# =============================================================================

class EraseRequest(BaseModel):
    """
    삭제 요청 페이로드.

    [보안 원칙]
      - hashed_user_id: SHA-256 해시 결과인 64자리 hex 고정 포맷만 허용.
        원본 user_id 또는 임의 문자열은 Pydantic 검증 단계에서 거부됩니다.
      - log_fields_to_anonymize: 항목별 최대 길이(PRIVACY_LOG_FIELD_MAX_LENGTH)를 검증.
        (각 항목은 이미 추출된 필드 값이어야 하며, PII 원문 포함 금지)
    """
    hashed_user_id: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 해시된 사용자 식별자 (64자리 hex, user_id 원문 금지)",
    )
    log_fields_to_anonymize: list[str] = Field(
        default_factory=list,
        description=(
            "익명화할 Interaction Log 필드 값 목록 (PII 원문 포함 금지). "
            f"항목당 최대 길이는 PRIVACY_LOG_FIELD_MAX_LENGTH 환경 변수로 제어 "
            f"(기본값: {_DEFAULT_LOG_FIELD_MAX_LENGTH}자)."
        ),
    )

    @field_validator("hashed_user_id")
    @classmethod
    def validate_sha256_hex(cls, v: str) -> str:
        """hashed_user_id가 SHA-256 hex(64자리) 포맷인지 검증합니다."""
        if not _SHA256_HEX_PATTERN.match(v):
            raise ValueError(
                "hashed_user_id must be a 64-character hexadecimal string (SHA-256 format). "
                "Raw user_id is not accepted."
            )
        return v.lower()  # 일관성을 위해 소문자로 정규화

    @field_validator("log_fields_to_anonymize", mode="after")
    @classmethod
    def validate_log_fields(cls, v: list[str]) -> list[str]:
        """
        log_fields_to_anonymize 각 항목의 최대 길이를 검증합니다.
        mode="after"를 사용하여 입력 이터러블이 이미 list[str]로 변환된 최종 상태에서 검증합니다.
        """
        max_length = _get_log_field_max_length()
        for idx, item in enumerate(v):
            if len(item) > max_length:
                raise ValueError(
                    f"log_fields_to_anonymize[{idx}] exceeds maximum allowed length "
                    f"({max_length} chars). Adjust PRIVACY_LOG_FIELD_MAX_LENGTH if needed."
                )
        return v


class AnonymizationFailureReason(str, Enum):
    """
    익명화 실패 시 클라이언트에 노출해도 안전한 정규화된 사유 코드.
    내부 구현 세부사항(예: 예외 클래스명)을 숨기고 API 스키마를 안정화합니다.
    """
    INVALID_INPUT = "invalid_input"
    INTERNAL_ERROR = "internal_error"
    ANONYMIZATION_FAILED = "anonymization_failed"
    UNKNOWN_ERROR = "unknown_error"


class AnonymizationSummary(BaseModel):
    """
    개별 로그 필드에 대한 익명화 처리 결과 요약 스키마.

    [설계 원칙]
      - 성공/실패 모두 동일한 스키마를 사용하여 클라이언트 파괴 위험 제거.
      - field_index: 요청 배열의 0-based 인덱스 — PII 없이 원본 필드와 매핑 가능.
      - 실패 시 key_version/rotation_policy/hash_name은 None.
      - 원문 필드 값(PII)은 절대 포함하지 않습니다.
    """
    field_index: int = Field(
        ...,
        description="요청 log_fields_to_anonymize 배열의 0-based 인덱스 (PII 미포함 매핑 키)",
    )
    success: bool = Field(..., description="해당 필드 익명화 성공 여부")
    key_version: Optional[int] = Field(
        default=None,
        description="사용된 키 버전 (성공 시에만 설정)",
    )
    rotation_policy: Optional[str] = Field(
        default=None,
        description="적용된 키 로테이션 정책 (성공 시에만 설정)",
    )
    hash_name: Optional[str] = Field(
        default=None,
        description="사용된 해시 알고리즘 이름 (성공 시에만 설정)",
    )
    reason: Optional[str] = Field(
        default=None,
        description="실패 또는 부분 성공 시 사유 코드 (PII 미포함). 하위 호환성을 위해 str 유지 (예: 'invalid_input')",
    )

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, v: Any) -> Optional[str]:
        """
        reason 필드에 어떤 타입이 들어오든 안전한 문자열로 중앙에서 정규화합니다.
        Enum이 들어오면 .value를 추출하고, 그 외의 알 수 없는 타입은 str()로 캐스팅하여 방어합니다.
        """
        if v is None:
            return None
        if isinstance(v, AnonymizationFailureReason):
            return v.value
        if not isinstance(v, str):
            return str(v)
        return v


class EraseResponse(BaseModel):
    """
    삭제 요청 처리 결과 응답 페이로드.
    모든 필드는 PII 원문을 포함하지 않습니다.
    """
    masked_user_id: str = Field(..., description="마스킹된 UID (PII 미포함)")
    deletion_success: bool = Field(..., description="Vector Data 삭제 성공 여부")
    db_rows_deleted: int = Field(..., description="DB 실제 삭제 행 수")
    anonymization_results: list[AnonymizationSummary] = Field(
        default_factory=list,
        description=(
            "각 로그 필드 익명화 처리 결과 요약 (PII 미포함). "
            "field_index로 요청 배열의 원본 항목과 매핑 가능."
        ),
    )
    audit_logged: bool = Field(
        ...,
        description=(
            "최종 감사 로그 기록 성공 여부. "
            "False인 경우 AuditConfigError가 발생하여 감사 파일 저장이 보장되지 않습니다."
        ),
    )
    message: str = Field(..., description="처리 결과 요약 메시지")


# =============================================================================
# E2E 오케스트레이션 헬퍼
# =============================================================================

def _build_anonymization_summary(
    field_index: int,
    result: AnonymizationResult,
) -> AnonymizationSummary:
    """
    AnonymizationResult를 AnonymizationSummary 타입 모델로 변환합니다.
    PII 원문(anonymized_value, salt_hex)은 포함하지 않습니다.
    """
    if not result.success:
        return _build_failed_summary(
            field_index,
            AnonymizationFailureReason.ANONYMIZATION_FAILED,
        )

    return AnonymizationSummary(
        field_index=field_index,
        success=True,
        key_version=result.key_version,
        rotation_policy=result.key_rotation_policy.value,
        hash_name=result.hash_name,
        reason=None,
    )


def _normalize_reason(
    reason: str | AnonymizationFailureReason | Exception | None,
) -> str:
    """
    익명화 실패 사유(reason)를 안전하고 일관된 문자열로 정규화하는 헬퍼 함수입니다.
    
    [보안 및 방어 로직]
    - Enum: .value 추출
    - Exception: PII 유출을 막기 위해 마스킹하고, 추적을 위해 서버 사이드에 로깅
    - None: 모호성을 없애기 위해 UNKNOWN_ERROR 사용
    - 그 외: 강제 str() 캐스팅
    """
    if reason is None:
        return AnonymizationFailureReason.UNKNOWN_ERROR.value
    if isinstance(reason, AnonymizationFailureReason):
        return reason.value
    if isinstance(reason, Exception):
        # 방어: 예외 객체가 그대로 넘어오면 메시지에 포함된 PII가 노출될 수 있으므로 마스킹
        # 보안(GDPR): 원본 에러 메시지(PII 포함 가능성)를 서버 로그에 남기지 않기 위해 
        # exc_info를 제외하고 메시지를 SHA-256 해싱하여 추적성(Traceability)만 확보합니다.
        msg_hash = hashlib.sha256(str(reason).encode("utf-8")).hexdigest()[:16]
        logger.error(
            "[OBS][PRIVACY][API] Implicit exception masking in _normalize_reason. "
            "Exception type: %s, msg_hash: %s", type(reason).__name__, msg_hash
        )
        return AnonymizationFailureReason.INTERNAL_ERROR.value
    if not isinstance(reason, str):
        return str(reason)
    return reason


def _build_failed_summary(
    field_index: int,
    reason: str | AnonymizationFailureReason | Exception | None,
) -> AnonymizationSummary:
    """
    실패한 익명화 항목을 AnonymizationSummary 타입 모델로 생성합니다.
    성공 경로와 동일한 스키마를 유지하여 클라이언트 일관성을 보장합니다.

    [타입 계약]
    _normalize_reason 헬퍼를 통해 어떠한 예기치 않은 타입이 들어오더라도 
    안전한 문자열로 캐스팅되어 모델에 주입됩니다.
    """
    return AnonymizationSummary(
        field_index=field_index,
        success=False,
        key_version=None,
        rotation_policy=None,
        hash_name=None,
        reason=_normalize_reason(reason),
    )


def _try_write_audit_log(**kwargs: Any) -> bool:
    """
    write_audit_log를 안전하게 호출하고 실제 기록 성공 여부를 반환합니다.

    [반환 정책]
      - True: 감사 로그 기록이 정상적으로 수행됨.
      - False: AuditConfigError(불변식 위반)가 발생하여 기록 실패.
    """
    try:
        write_audit_log(**kwargs)
        return True
    except AuditConfigError as e:
        logger.error(
            "[OBS][PRIVACY][API] Audit log write failed (AuditConfigError): %s",
            type(e).__name__,
        )
        return False


def _build_erase_message(
    deletion_success: bool,
    anonymization_failed_count: int,
) -> str:
    """
    삭제 및 익명화 결과를 모두 반영한 처리 결과 메시지를 생성합니다.
    deletion_success와 익명화 실패 건수를 모두 고려하여 호출자를 오도하지 않습니다.
    """
    if not deletion_success:
        return "삭제가 부분적으로 처리되었습니다. 감사 로그를 확인해 주세요."
    if anonymization_failed_count > 0:
        return (
            f"삭제는 완료되었으나 {anonymization_failed_count}건의 익명화가 실패했습니다. "
            "감사 로그를 확인해 주세요."
        )
    return "삭제 및 익명화 처리가 완료되었습니다."


# =============================================================================
# 엔드포인트
# =============================================================================

@router.post(
    "/erase",
    response_model=EraseResponse,
    status_code=status.HTTP_200_OK,
    summary="사용자 데이터 삭제 요청 (GDPR 제17조)",
    description=(
        "Vector Data 물리 삭제 → Interaction Log 익명화 → 감사 로그 기록을 "
        "단일 원자적 흐름으로 처리합니다. 인증 필수."
    ),
)
async def erase_user_data(
    request: EraseRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> EraseResponse:
    """
    GDPR Right-to-Erasure 처리 파이프라인 E2E 엔드포인트.

    [처리 순서]
      1. 요청 수신 감사 로그 기록 (DATA_DELETE_REQUESTED)
      2. 2단계: Vector Data 삭제 (delete_user_data)
      3. 3단계: Interaction Log 익명화 (anonymize_log_entry, 각 필드별 — field_index 추적)
      4. 최종 처리 결과 감사 로그 기록 — 실제 기록 성공 여부를 audit_logged에 반영

    [Graceful Degradation]
      - delete_user_data() 예외 → 500 반환 + FAILURE 감사 로그
      - 익명화 실패 → 해당 필드만 실패, 전체 파이프라인 유지
      - 감사 로그 기록 실패 → audit_logged=False 반환, 프로세스 중단 없음
    """
    hashed_uid = request.hashed_user_id
    masked = mask_uid(hashed_uid)

    # ── 1. 요청 수신 감사 로그 ──────────────────────────────────────────────
    _try_write_audit_log(
        event_type=AuditEventType.DATA_DELETE_REQUESTED,
        masked_uid=masked,
        result="erase_request_received",
        extra={
            "log_fields_count": len(request.log_fields_to_anonymize),
            "requester_role": current_user.get("role", "unknown"),
        },
    )

    # ── 2. Vector Data 삭제 (2단계) ─────────────────────────────────────────
    deletion_result: DeletionResult
    try:
        deletion_result = await delete_user_data(hashed_uid)
    except Exception as exc:
        # 예외 타입명만 로그 — str(exc) 제외로 PII 유출 방지
        logger.exception(
            "[OBS][PRIVACY][API] Vector data deletion failed: masked_uid=%s, error_type=%s",
            masked, type(exc).__name__,
        )
        _try_write_audit_log(
            event_type=AuditEventType.DATA_DELETE_FAILURE,
            masked_uid=masked,
            result=f"deletion_pipeline_error: {type(exc).__name__}",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="삭제 처리 중 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc

    # ── 3. Interaction Log 익명화 (3단계) ───────────────────────────────────
    # field_index를 통해 클라이언트가 PII 없이 실패 항목을 원본과 매핑 가능
    anonymization_summaries: list[AnonymizationSummary] = []
    for field_index, field_value in enumerate(request.log_fields_to_anonymize):
        try:
            anon_result: AnonymizationResult = await anonymize_log_entry(
                hashed_user_id=hashed_uid,
                log_field_value=field_value,
            )
            anonymization_summaries.append(
                _build_anonymization_summary(field_index, anon_result)
            )
        except ValueError:
            # str(ve) 제외 — ValueError 메시지에 PII 포함 가능성 차단
            logger.warning(
                "[OBS][PRIVACY][API] Anonymization skipped: masked_uid=%s, "
                "field_index=%d, reason=invalid_input",
                masked, field_index,
            )
            anonymization_summaries.append(
                _build_failed_summary(field_index, AnonymizationFailureReason.INVALID_INPUT)
            )
        except Exception as exc:
            # 예기치 않은 오류 — 해당 필드만 실패, Graceful Degradation
            logger.exception(
                "[OBS][PRIVACY][API] Anonymization error: masked_uid=%s, "
                "field_index=%d, error_type=%s",
                masked, field_index, type(exc).__name__,
            )
            # 내부 구현 세부사항(예외 클래스명)을 API 응답 스키마에 노출하지 않기 위해
            # 예기치 않은 오류는 안정적인 공통 코드로 매핑합니다.
            anonymization_summaries.append(
                _build_failed_summary(field_index, AnonymizationFailureReason.INTERNAL_ERROR)
            )

    # ── 4. 최종 처리 결과 감사 로그 (실제 기록 성공 여부 추적) ──────────────
    anonymization_failed_count: int = sum(
        1 for s in anonymization_summaries if not s.success
    )
    all_anon_success: bool = anonymization_failed_count == 0
    final_event = (
        AuditEventType.DATA_DELETE_SUCCESS
        if deletion_result.success and all_anon_success
        else AuditEventType.DATA_DELETE_FAILURE
    )
    audit_logged: bool = _try_write_audit_log(
        event_type=final_event,
        masked_uid=masked,
        result="erase_pipeline_complete",
        extra={
            "deletion_success": deletion_result.success,
            "db_rows_deleted": deletion_result.db_rows_deleted,
            "anonymization_total": len(anonymization_summaries),
            "anonymization_failed": anonymization_failed_count,
            "vacuum_triggered": deletion_result.vacuum_triggered,
            "compaction_recommended": deletion_result.compaction_recommended,
        },
    )

    logger.info(
        "[OBS][PRIVACY][API] Erase pipeline complete: masked_uid=%s, "
        "deletion_success=%s, db_rows=%d, anon_total=%d, anon_failed=%d, audit_logged=%s",
        masked,
        deletion_result.success,
        deletion_result.db_rows_deleted,
        len(anonymization_summaries),
        anonymization_failed_count,
        audit_logged,
    )

    return EraseResponse(
        masked_user_id=masked,
        deletion_success=deletion_result.success,
        db_rows_deleted=deletion_result.db_rows_deleted,
        anonymization_results=anonymization_summaries,
        audit_logged=audit_logged,
        message=_build_erase_message(
            deletion_success=deletion_result.success,
            anonymization_failed_count=anonymization_failed_count,
        ),
    )

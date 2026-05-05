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
  - PII가 포함될 수 있는 예외 메시지(str(exception))는 로그에 기록하지 않으며,
    예외 타입명만 기록합니다.
  - 모든 처리 결과는 audit_logger를 통해 감사 로그에 기록됩니다.
  - 인증 의존성(get_current_user)은 기존 deps.py 패턴을 재사용합니다.

[Graceful Degradation 정책]
  - `delete_user_data()` 내부 예외 → 파이프라인 전체 중단, 500 반환 + FAILURE 감사 로그
    (FAISS/Redis 삭제 실패는 delete_user_data 내부에서 부분 성공으로 처리)
  - 익명화 실패 → 해당 필드만 실패 처리, 전체 파이프라인 유지
  - 감사 로그 기록 실패 → `audit_logged=False`로 응답에 정확히 반영, 프로세스 중단 없음

[환경 변수 의존성]
  - AUDIT_LOG_BACKEND, PBKDF2_ITERATIONS 등 — privacy_service.py / audit_logger.py 참조
"""

from __future__ import annotations

import logging
import re
from typing import Any

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


# =============================================================================
# 요청/응답 모델
# =============================================================================

class EraseRequest(BaseModel):
    """
    삭제 요청 페이로드.

    [보안 원칙]
      - hashed_user_id: SHA-256 해시 결과인 64자리 hex 고정 포맷만 허용.
        원본 user_id 또는 임의 문자열은 Pydantic 검증 단계에서 거부됩니다.
      - log_fields_to_anonymize: 익명화 대상 Interaction Log 필드 값 목록.
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
        description="익명화할 Interaction Log 필드 값 목록 (PII 원문 포함 금지)",
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


class EraseResponse(BaseModel):
    """
    삭제 요청 처리 결과 응답 페이로드.
    모든 필드는 PII 원문을 포함하지 않습니다.
    """
    masked_user_id: str = Field(..., description="마스킹된 UID (PII 미포함)")
    deletion_success: bool = Field(..., description="Vector Data 삭제 성공 여부")
    db_rows_deleted: int = Field(..., description="DB 실제 삭제 행 수")
    anonymization_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="각 로그 필드 익명화 처리 결과 요약 (PII 미포함)",
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

def _build_anonymization_summary(result: AnonymizationResult) -> dict[str, Any]:
    """
    AnonymizationResult를 응답용 요약 딕셔너리로 변환합니다.
    PII 원문(anonymized_value, salt_hex)은 응답에 포함하지 않습니다.
    """
    return {
        "success": result.success,
        "key_version": result.key_version,
        "rotation_policy": result.key_rotation_policy.value,
        "hash_name": result.hash_name,
        # anonymized_value와 salt_hex는 내부 감사 전용 — 응답에 노출 금지
    }


def _try_write_audit_log(**kwargs: Any) -> bool:
    """
    write_audit_log를 안전하게 호출하고 실제 기록 성공 여부를 반환합니다.

    [반환 정책]
      - True: 감사 로그 기록이 정상적으로 수행됨.
      - False: AuditConfigError(불변식 위반)가 발생하여 감사 로그 기록 실패.
        (audit_logger 내부 파일 I/O 오류 폴백은 True를 반환 — 표준 로거에 기록됨)
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
    삭제 및 익명화 결과를 모두 반영한 정확한 처리 결과 메시지를 생성합니다.
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
      3. 3단계: Interaction Log 익명화 (anonymize_log_entry, 각 필드별)
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
    anonymization_summaries: list[dict[str, Any]] = []
    for field_value in request.log_fields_to_anonymize:
        try:
            anon_result: AnonymizationResult = await anonymize_log_entry(
                hashed_user_id=hashed_uid,
                log_field_value=field_value,
            )
            anonymization_summaries.append(_build_anonymization_summary(anon_result))
        except ValueError:
            # str(ve) 제외 — ValueError 메시지에 PII 포함 가능성 차단
            logger.warning(
                "[OBS][PRIVACY][API] Anonymization skipped: masked_uid=%s, reason=invalid_input",
                masked,
            )
            anonymization_summaries.append({"success": False, "reason": "invalid_input"})
        except Exception as exc:
            # 예기치 않은 오류 — 해당 필드만 실패, Graceful Degradation
            logger.exception(
                "[OBS][PRIVACY][API] Anonymization error: masked_uid=%s, error_type=%s",
                masked, type(exc).__name__,
            )
            anonymization_summaries.append(
                {"success": False, "reason": type(exc).__name__}
            )

    # ── 4. 최종 처리 결과 감사 로그 (실제 기록 성공 여부 추적) ──────────────
    anonymization_failed_count: int = sum(
        1 for s in anonymization_summaries if not s.get("success", False)
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

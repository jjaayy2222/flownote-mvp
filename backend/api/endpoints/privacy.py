# backend/api/endpoints/privacy.py

"""
GDPR Right-to-Erasure API Endpoint — v9.0 Phase 2-4 (Integration & Compliance)
=================================================================================

[역할]
  - 사용자 삭제 요청(Right to Erasure, GDPR 제17조)의 단일 API 진입점.
  - 2단계(Vector Data 삭제) → 3단계(Interaction Log 익명화) → 1단계(감사 로그 기록)
    순서를 오케스트레이션합니다.

[보안 설계]
  - hashed_user_id만 내부 파이프라인에 전달하며, user_id 원문은 이 레이어에 진입하지 않습니다.
  - 모든 처리 결과는 audit_logger를 통해 감사 로그에 기록됩니다.
  - 인증 의존성(get_current_user)은 기존 deps.py 패턴을 재사용합니다.

[Graceful Degradation 정책]
  - FAISS/Redis 삭제 실패 → DB 삭제 유지 + 감사 로그 FAILURE 기록 + 재시도 큐 적재 권장
  - 익명화 실패 → 삭제 결과는 반환, 익명화 실패 감사 로그 별도 기록
  - 감사 로그 기록 실패 → audit_logger 내부에서 표준 로거 폴백 처리 (파이프라인 중단 없음)

[환경 변수 의존성]
  - AUDIT_LOG_BACKEND, PBKDF2_ITERATIONS 등 — privacy_service.py / audit_logger.py 참조
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.api.deps import get_current_user
from backend.core.audit_logger import AuditEventType, mask_uid, write_audit_log
from backend.services.privacy_service import (
    AnonymizationResult,
    DeletionResult,
    anonymize_log_entry,
    delete_user_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/privacy", tags=["privacy"])


# =============================================================================
# 요청/응답 모델
# =============================================================================

class EraseRequest(BaseModel):
    """
    삭제 요청 페이로드.

    [보안 원칙]
      - hashed_user_id: SHA-256 등으로 해시된 사용자 식별자. user_id 원문 절대 금지.
      - log_fields_to_anonymize: 익명화 대상 Interaction Log 필드 값 목록.
        (각 항목은 이미 추출된 필드 값이어야 하며, PII 원문 포함 금지)
    """
    hashed_user_id: str = Field(
        ...,
        min_length=1,
        description="SHA-256 해시된 사용자 식별자 (user_id 원문 금지)",
    )
    log_fields_to_anonymize: list[str] = Field(
        default_factory=list,
        description="익명화할 Interaction Log 필드 값 목록 (PII 원문 포함 금지)",
    )


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
    audit_logged: bool = Field(..., description="감사 로그 기록 성공 여부")
    message: str = Field(..., description="처리 결과 요약 메시지")


# =============================================================================
# E2E 오케스트레이션 헬퍼
# =============================================================================

def _build_anonymization_summary(result: AnonymizationResult) -> dict[str, Any]:
    """
    AnonymizationResult를 응답용 요약 딕셔너리로 변환합니다.
    PII 원문(anonymized_value 실제값)은 응답에 포함하지 않습니다.
    """
    return {
        "success": result.success,
        "key_version": result.key_version,
        "rotation_policy": result.key_rotation_policy.value,
        "hash_name": result.hash_name,
        # anonymized_value와 salt_hex는 응답에 노출하지 않음 (내부 감사 전용)
    }


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
      4. 최종 처리 결과 감사 로그 기록

    [Graceful Degradation]
      - 삭제 서비스 내부 예외 → 500 반환 및 감사 로그 FAILURE 기록
      - 익명화 실패 → 개별 필드 실패로 기록, 전체 파이프라인 중단 없음
    """
    hashed_uid = request.hashed_user_id
    masked = mask_uid(hashed_uid)

    # ── 1. 요청 수신 감사 로그 ──────────────────────────────────────────────
    write_audit_log(
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
        logger.exception(
            "[OBS][PRIVACY][API] Vector data deletion failed: masked_uid=%s, error=%s",
            masked, type(exc).__name__,
        )
        write_audit_log(
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
        except ValueError as ve:
            # 입력값 오류 (빈 값 등) — 해당 필드만 실패 처리, 파이프라인 유지
            logger.warning(
                "[OBS][PRIVACY][API] Anonymization skipped for a field: masked_uid=%s, reason=%s",
                masked, str(ve),
            )
            anonymization_summaries.append({"success": False, "reason": "invalid_input"})
        except Exception as exc:
            # 예기치 않은 오류 — 해당 필드만 실패, Graceful Degradation
            logger.exception(
                "[OBS][PRIVACY][API] Anonymization error for a field: masked_uid=%s, error=%s",
                masked, type(exc).__name__,
            )
            anonymization_summaries.append(
                {"success": False, "reason": type(exc).__name__}
            )

    # ── 4. 최종 처리 결과 감사 로그 ─────────────────────────────────────────
    all_anon_success = all(s.get("success", False) for s in anonymization_summaries)
    final_event = (
        AuditEventType.DATA_DELETE_SUCCESS
        if deletion_result.success and all_anon_success
        else AuditEventType.DATA_DELETE_FAILURE
    )
    write_audit_log(
        event_type=final_event,
        masked_uid=masked,
        result="erase_pipeline_complete",
        extra={
            "deletion_success": deletion_result.success,
            "db_rows_deleted": deletion_result.db_rows_deleted,
            "anonymization_total": len(anonymization_summaries),
            "anonymization_failed": sum(
                1 for s in anonymization_summaries if not s.get("success", False)
            ),
            "vacuum_triggered": deletion_result.vacuum_triggered,
            "compaction_recommended": deletion_result.compaction_recommended,
        },
    )

    logger.info(
        "[OBS][PRIVACY][API] Erase pipeline complete: masked_uid=%s, "
        "deletion_success=%s, db_rows=%d, anon_total=%d",
        masked,
        deletion_result.success,
        deletion_result.db_rows_deleted,
        len(anonymization_summaries),
    )

    return EraseResponse(
        masked_user_id=masked,
        deletion_success=deletion_result.success,
        db_rows_deleted=deletion_result.db_rows_deleted,
        anonymization_results=anonymization_summaries,
        audit_logged=True,
        message=(
            "삭제 및 익명화 처리가 완료되었습니다."
            if deletion_result.success
            else "삭제가 부분적으로 처리되었습니다. 감사 로그를 확인해 주세요."
        ),
    )

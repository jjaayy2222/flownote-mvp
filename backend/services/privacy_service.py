# backend/services/privacy_service.py

"""
GDPR Right-to-Erasure — v9.0 Phase 2-4 (Privacy Pipeline ②)
=============================================================

사용자 삭제 요청(GDPR 제17조 잊혀질 권리)에 대응하는 Vector Data 완전 삭제 파이프라인.

[설계 원칙]
  - PII 마스킹: hashed_user_id만 처리 대상으로 삼고, user_id 원문은 이 모듈에 진입하기 전 해시화.
  - 하드코딩 금지: 스케줄·임계값 등 모든 설정은 환경 변수로 외부화.
  - 감사 로그 연동: 모든 삭제·실패 이벤트는 audit_logger를 통해 90일 보관 정책에 기록.
  - 트랜잭션 보장: DB 레코드 삭제는 단일 트랜잭션으로 처리하여 부분 삭제 방지.

[삭제 흐름]
  1. DB 레코드 물리적 삭제 (SQL DELETE, 트랜잭션)
  2. VACUUM 트리거 조건 판단 (스케줄 또는 누적 임계값)
  3. FAISS 서브-인덱스 파일 및 Redis 메타데이터 영구 제거
  4. 컴팩션(Compaction) 트리거 신호 발송
  5. 감사 이벤트 기록 (성공/실패)

[환경 변수]
  - VACUUM_SCHEDULE_CRON   [str, 기본값: "0 2 * * *"]  — 정기 VACUUM cron 표현식
  - VACUUM_BATCH_THRESHOLD [int, 기본값: 1000, 범위: 1~100_000] — 누적 삭제 임계값

[주요 참조처 (Consumers)]
  - backend.api 또는 Celery 태스크: delete_user_data() 호출
  - backend.core.audit_logger: 감사 이벤트 기록
  - backend.services.personalized_index_service: FAISS 인덱스 제거
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypedDict

from backend.core.audit_logger import (
    AuditEventType,
    mask_uid,
    write_audit_log,
)
from backend.services.personalized_index_service import (
    build_index_path,
    delete_index_metadata,
    should_rebuild_index,
    load_index_metadata,
)

logger = logging.getLogger(__name__)

# =============================================================================
# 모듈 레벨 상수 (하드코딩 금지 — 환경 변수 우선)
# =============================================================================

# 정기 VACUUM cron 표현식
_VACUUM_SCHEDULE_CRON_ENV_KEY = "VACUUM_SCHEDULE_CRON"
_DEFAULT_VACUUM_SCHEDULE_CRON = "0 2 * * *"

# 누적 삭제 건수 VACUUM 임계값
_VACUUM_BATCH_THRESHOLD_ENV_KEY = "VACUUM_BATCH_THRESHOLD"
_DEFAULT_VACUUM_BATCH_THRESHOLD = 1_000
_MIN_VACUUM_BATCH_THRESHOLD = 1
_MAX_VACUUM_BATCH_THRESHOLD = 100_000

# 누적 삭제 카운터 (인프라 공유 없이 프로세스 내 카운팅 — 재시작 시 초기화됨)
# 운영 환경에서는 Redis 또는 DB 기반 영속 카운터로 교체 권장
_deletion_batch_counter: int = 0


def _load_vacuum_batch_threshold() -> int:
    """
    VACUUM_BATCH_THRESHOLD 환경 변수를 파싱하여 반환합니다.
    파싱 실패 또는 범위 이탈 시 WARNING 로그 후 기본값으로 폴백합니다.
    """
    raw = os.getenv(_VACUUM_BATCH_THRESHOLD_ENV_KEY)
    default = _DEFAULT_VACUUM_BATCH_THRESHOLD

    if raw is None:
        return default

    try:
        value = int(raw)
        if not (_MIN_VACUUM_BATCH_THRESHOLD <= value <= _MAX_VACUUM_BATCH_THRESHOLD):
            logger.warning(
                "[OBS][PRIVACY][CONFIG] '%s'=%d is outside safe range [%d, %d]. "
                "Falling back to default %d.",
                _VACUUM_BATCH_THRESHOLD_ENV_KEY,
                value,
                _MIN_VACUUM_BATCH_THRESHOLD,
                _MAX_VACUUM_BATCH_THRESHOLD,
                default,
            )
            return default
        return value
    except (ValueError, TypeError):
        logger.warning(
            "[OBS][PRIVACY][CONFIG] '%s'=%r is not a valid integer. "
            "Falling back to default %d.",
            _VACUUM_BATCH_THRESHOLD_ENV_KEY,
            raw,
            default,
        )
        return default


def get_vacuum_schedule_cron() -> str:
    """VACUUM_SCHEDULE_CRON 환경 변수를 반환합니다 (미설정 시 기본값)."""
    return (
        os.getenv(_VACUUM_SCHEDULE_CRON_ENV_KEY, "").strip()
        or _DEFAULT_VACUUM_SCHEDULE_CRON
    )


def get_vacuum_batch_threshold() -> int:
    """
    VACUUM_BATCH_THRESHOLD 값을 반환합니다.
    테스트 환경에서 monkeypatch 대상으로 활용 가능.
    """
    return _load_vacuum_batch_threshold()


# =============================================================================
# 결과 타입 정의 (TypedDict)
# =============================================================================

class DeletionResult(TypedDict):
    """
    delete_user_data() 반환값의 타입 계약.
    모든 필드는 항상 존재하며, 타입 검사기가 호출측에서 올바른 체크를 수행할 수 있도록 보장합니다.
    """
    masked_user_id: str        # 마스킹된 UID (masked_uid, 원문 PII 미사용)
    hashed_user_id: str        # [DEPRECATED] 이전 API 호환성을 위해 유지 (masked_user_id와 동일)
    db_rows_deleted: int       # DB 레코드 실제 삭제 행 수
    db_deleted: bool           # DB 레코드가 1건 이상 삭제되었는지 여부 (계약 명확화)
    faiss_file_removed: bool   # FAISS 인덱스 파일 물리 삭제 성공 여부
    redis_meta_deleted: bool   # Redis 메타데이터 삭제 성공 여부
    compaction_recommended: bool  # FAISS Compaction 권장 여부
    vacuum_triggered: bool     # VACUUM 즉시 실행 권장 여부
    success: bool              # FAISS 파일 + Redis 메타 삭제 전체 성공 여부 (DB 0행은 멱등 성공으로 허용)


def _init_deletion_result(masked_uid: str) -> DeletionResult:
    """초기 결과 객체를 생성하여 masked_user_id와 hashed_user_id가 항상 동일함을 보장합니다."""
    return {
        "masked_user_id": masked_uid,
        "hashed_user_id": masked_uid,
        "db_rows_deleted": 0,
        "db_deleted": False,
        "faiss_file_removed": False,
        "redis_meta_deleted": False,
        "compaction_recommended": False,
        "vacuum_triggered": False,
        "success": False,
    }


def _finalize_deletion_result(result: DeletionResult) -> DeletionResult:
    """결과 객체의 불변식(invariant)을 검증하고, 파생 필드를 계산하여 최종 반환합니다."""
    # db_deleted가 파이프라인 중간에 임의로 변경되지 않았는지(초기값 False인지) 검증
    # Python -O 옵션에 의해 무시될 수 있는 assert 대신 명시적 예외를 발생시킵니다.
    # 키가 존재하지 않으면 KeyError를 그대로 발생시켜 구조 자체의 불변식 위반을 드러냅니다.
    if result["db_deleted"] is not False:
        raise ValueError("db_deleted must not be modified directly. It is a derived field.")
    
    # 원본 객체를 직접 변조(mutate)하지 않고 얕은 복사본을 생성하여 반환 (Immutability)
    # DeletionResult는 모든 필드가 원시 타입(primitive)이므로 얕은 복사로 충분히 불변성이 보장됩니다.
    final_result = result.copy()
    final_result["db_deleted"] = final_result["db_rows_deleted"] > 0
    return final_result


# =============================================================================
# 공개 API
# =============================================================================

__all__ = [
    "DeletionResult",
    "delete_user_data",
    "trigger_vacuum_if_needed",
    "get_vacuum_schedule_cron",
    "get_vacuum_batch_threshold",
]


# =============================================================================
# VACUUM 트리거 판단
# =============================================================================

def _increment_deletion_counter() -> int:
    """
    프로세스 내 누적 삭제 카운터를 1 증가시키고 현재 값을 반환합니다.

    [동시성 주의사항]
    이 카운터는 프로세스 메모리의 전역 변수이므로 다음 제약이 있습니다:
    - CPython GIL 환경에서도 멀티스레드 동시 호출 시 정확한 집계를 보장하지 않습니다.
    - 멀티프로세스(Gunicorn 워커, Celery 워커 등) 환경에서는 워커 간 카운터가 공유되지 않습니다.
    - 서버 재시작 시 초기화됩니다.
    운영 환경에서는 Redis INCR 또는 DB 기반 카운터로 교체하여 영속성과 정합성을 보장하세요.
    """
    global _deletion_batch_counter
    _deletion_batch_counter += 1
    return _deletion_batch_counter


def trigger_vacuum_if_needed(current_count: int) -> bool:
    """
    누적 삭제 건수가 VACUUM_BATCH_THRESHOLD 이상이면 VACUUM 트리거 신호를 반환합니다.
    실제 VACUUM 실행은 호출자(스케줄러 or API 레이어)가 수행합니다.

    [트리거 조건]
      1. 정기 스케줄(VACUUM_SCHEDULE_CRON): 스케줄러가 직접 호출
      2. 누적 임계값 이상(>=): 이 함수가 True를 반환할 때 즉시 실행 권장

    Args:
        current_count: 현재까지의 누적 삭제 건수

    Returns:
        True이면 VACUUM 즉시 실행 권장, False이면 스케줄 대기
    """
    threshold = get_vacuum_batch_threshold()
    if current_count >= threshold:
        logger.info(
            "[OBS][PRIVACY] VACUUM trigger condition met: "
            "accumulated_deletions=%d >= threshold=%d.",
            current_count,
            threshold,
        )
        return True
    return False


# =============================================================================
# FAISS 인덱스 파일 물리 삭제
# =============================================================================

def _remove_faiss_index_file(index_path: Path) -> bool:
    """
    FAISS 서브-인덱스 파일을 물리적으로 삭제합니다.

    `unlink(missing_ok=True)`를 사용하여 exists()체크와 unlink() 사이의
    TOCTOU(검사 시점 vs 사용 시점) 레이스 컨디션을 회피합니다.

    Args:
        index_path: build_index_path()가 반환한 Path 객체

    Returns:
        True: 파일 삭제 성공 또는 원래 없었음, False: 삭제 실패(예외 발생)
    """
    try:
        index_path.unlink(missing_ok=True)
        logger.info(
            "[OBS][PRIVACY] FAISS index file permanently removed: path=%s, suffix=%s",
            index_path,
            index_path.suffix,
        )
        return True
    except OSError as e:
        logger.exception(
            "[OBS][PRIVACY] Failed to remove FAISS index file at path=%s, error_type=%s, error_msg=%s. "
            "Manual cleanup may be required.",
            index_path,
            type(e).__name__,
            str(e),
        )
        return False


# =============================================================================
# 핵심 삭제 파이프라인
# =============================================================================

async def delete_user_data(
    hashed_user_id: str,
    storage_base_path: str,
    db_delete_fn: Callable[[str], Awaitable[int]],
) -> DeletionResult:
    """
    GDPR 제17조(잊혀질 권리)에 따른 사용자 Vector Data 완전 삭제 파이프라인.

    [처리 순서]
      1. DB 레코드 물리적 삭제 (트랜잭션 보장은 db_delete_fn 구현체 책임)
      2. 누적 카운터 증가 및 VACUUM 필요 여부 판단
      3. FAISS 인덱스 파일 물리 삭제
      4. Redis 메타데이터 삭제 (delete_index_metadata)
      5. FAISS 컴팩션 권장 여부 확인 (should_rebuild_index)
      6. 감사 이벤트 기록

    [의존성 주입 원칙]
      db_delete_fn을 외부에서 주입받으므로 특정 DB ORM에 결합하지 않습니다.
      실제 호출자(API 핸들러 또는 Celery 태스크)가 DB 세션을 포함한 삭제 함수를 제공합니다.

    Args:
        hashed_user_id:    compute_hashed_user_id()의 반환값 (PII 미포함).
        storage_base_path: PersonalizedRAGConfig.storage_base_path.
        db_delete_fn:      async callable — 서명: (hashed_user_id: str) -> int (삭제된 행 수)

    Returns:
        실행 결과 딕셔너리:
            {
                "hashed_user_id": masked_uid (마스킹),
                "db_rows_deleted": int,
                "faiss_file_removed": bool,
                "redis_meta_deleted": bool,
                "compaction_recommended": bool,
                "vacuum_triggered": bool,
                "success": bool,
            }

    Raises:
        ValueError: hashed_user_id 또는 storage_base_path가 비어있는 경우
    """
    if not hashed_user_id:
        raise ValueError("delete_user_data: 'hashed_user_id' must not be empty.")
    if not storage_base_path:
        raise ValueError("delete_user_data: 'storage_base_path' must not be empty.")

    masked = mask_uid(hashed_user_id)
    result: DeletionResult = _init_deletion_result(masked)

    # ── 1. DB 레코드 물리적 삭제 ──────────────────────────────────────────
    write_audit_log(
        event_type=AuditEventType.DATA_DELETE_REQUESTED,
        masked_uid=masked,
        result="initiated",
    )

    try:
        rows_deleted: int = await db_delete_fn(hashed_user_id)
        result["db_rows_deleted"] = rows_deleted
        if rows_deleted == 0:
            logger.info(
                "[OBS][PRIVACY] DB records already deleted (idempotent): rows=%d, masked_uid=%s",
                rows_deleted,
                masked,
            )
        else:
            logger.info(
                "[OBS][PRIVACY] DB records deleted: rows=%d, masked_uid=%s",
                rows_deleted,
                masked,
            )
    except Exception as e:
        logger.error(
            "[OBS][PRIVACY] DB deletion failed for masked_uid=%s: %s",
            masked,
            type(e).__name__,
            exc_info=True,
        )
        write_audit_log(
            event_type=AuditEventType.DATA_DELETE_FAILURE,
            masked_uid=masked,
            result=f"db_deletion_failed: {type(e).__name__}",
        )
        return _finalize_deletion_result(result)

    # ── 2. 누적 카운터 및 VACUUM 트리거 판단 ──────────────────────────────
    current_count = _increment_deletion_counter()
    vacuum_needed = trigger_vacuum_if_needed(current_count)
    result["vacuum_triggered"] = vacuum_needed

    if vacuum_needed:
        logger.info(
            "[OBS][PRIVACY] VACUUM recommended (schedule: %s, threshold: %d). "
            "Caller is responsible for executing VACUUM.",
            get_vacuum_schedule_cron(),
            get_vacuum_batch_threshold(),
        )

    # ── 3. FAISS 인덱스 파일 물리 삭제 ───────────────────────────────────
    index_path = build_index_path(hashed_user_id, storage_base_path)
    faiss_removed = _remove_faiss_index_file(index_path)
    result["faiss_file_removed"] = faiss_removed

    # ── 4. Redis 메타데이터 삭제 ──────────────────────────────────────────
    redis_meta_deleted = False
    try:
        # 컴팩션 필요 여부를 삭제 전 메타데이터로 판단
        existing_meta = await load_index_metadata(hashed_user_id)
        if existing_meta is not None:
            compaction_recommended = should_rebuild_index(existing_meta)
            result["compaction_recommended"] = compaction_recommended
            if compaction_recommended:
                logger.info(
                    "[OBS][PRIVACY] Compaction recommended for masked_uid=%s "
                    "(deleted_count=%d, vector_count=%d).",
                    masked,
                    existing_meta.deleted_count,
                    existing_meta.vector_count,
                )

        await delete_index_metadata(hashed_user_id)
        redis_meta_deleted = True
        logger.info(
            "[OBS][PRIVACY] Redis index metadata deleted for masked_uid=%s.",
            masked,
        )
    except Exception as e:
        logger.error(
            "[OBS][PRIVACY] Redis metadata deletion failed for masked_uid=%s: %s",
            masked,
            type(e).__name__,
            exc_info=True,
        )

    result["redis_meta_deleted"] = redis_meta_deleted

    # ── 5. 최종 결과 판단 및 감사 로그 기록 ─────────────────────────
    # FAISS 파일 + Redis 메타 삭제가 모두 성공이면 `success=True`.
    # rows_deleted == 0인 경우에도 예외가 없다면(애초에 삭제할 데이터가 없었던 경우)
    # 멱등적 성공으로 처리합니다. DB 예외는 위에서 조기 리턴하므로 여기 도달 시 DB 단계는 무결합니다.
    # 모든 조건을 AND로 연결하여 조용한 실패를 구조적으로 탐지합니다.
    overall_success = faiss_removed and redis_meta_deleted
    result["success"] = overall_success

    if overall_success:
        is_idempotent = result["db_rows_deleted"] == 0
        write_audit_log(
            event_type=AuditEventType.DATA_DELETE_SUCCESS,
            masked_uid=masked,
            result="idempotent_success" if is_idempotent else "success",
            extra={
                "db_rows_deleted": result["db_rows_deleted"],
                "faiss_file_removed": faiss_removed,
                "redis_meta_deleted": redis_meta_deleted,
                "compaction_recommended": result["compaction_recommended"],
                "vacuum_triggered": vacuum_needed,
            },
        )
        if is_idempotent:
            logger.info(
                "[OBS][PRIVACY] User data deletion pipeline completed idempotently (no DB rows). masked_uid=%s",
                masked,
            )
        else:
            logger.info(
                "[OBS][PRIVACY] User data deletion pipeline completed successfully. masked_uid=%s",
                masked,
            )
    else:
        write_audit_log(
            event_type=AuditEventType.DATA_DELETE_FAILURE,
            masked_uid=masked,
            result="partial_failure",
            extra={
                "faiss_file_removed": faiss_removed,
                "redis_meta_deleted": redis_meta_deleted,
            },
        )
        logger.warning(
            "[OBS][PRIVACY] User data deletion pipeline partially failed. "
            "masked_uid=%s, faiss_removed=%s, redis_deleted=%s",
            masked,
            faiss_removed,
            redis_meta_deleted,
        )

    # ── 최종 파생 필드 계산 및 반환 ──
    # 캡슐화된 헬퍼를 통해 중간 상태 변조를 검증하고 파생 필드를 계산합니다.
    return _finalize_deletion_result(result)

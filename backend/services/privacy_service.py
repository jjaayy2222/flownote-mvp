# backend/services/privacy_service.py

"""
GDPR Right-to-Erasure — v9.0 Phase 2-5 (Privacy Pipeline ②③)
==============================================================

사용자 삭제 요청(GDPR 제17조 잊혀질 권리)에 대응하는 완전 삭제 및 익명화 파이프라인.

[설계 원칙]
  - PII 마스킹: hashed_user_id만 처리 대상으로 삼고, user_id 원문은 이 모듈에 진입하기 전 해시화.
  - 하드코딩 금지: 스케줄·임계값·반복횟수 등 모든 설정은 환경 변수로 외부화.
  - 감사 로그 연동: 모든 삭제·익명화·실패 이벤트는 audit_logger를 통해 90일 보관 정책에 기록.
  - 트랜잭션 보장: DB 레코드 삭제는 단일 트랜잭션으로 처리하여 부분 삭제 방지.
  - NIST SP 800-132 준수: PBKDF2 파라미터는 엔트로피 최소 요건을 런타임에 검증.

[삭제·익명화 흐름]
  1. DB 레코드 물리적 삭제 (SQL DELETE, 트랜잭션)
  2. VACUUM 트리거 조건 판단 (스케줄 또는 누적 임계값)
  3. FAISS 서브-인덱스 파일 및 Redis 메타데이터 영구 제거
  4. 컴팩션(Compaction) 트리거 신호 발송
  5. 감사 이벤트 기록 (성공/실패)
  6. [익명화] Interaction Log PBKDF2-HMAC-SHA256 익명화
  7. [익명화] 키 로테이션 버전 관리 (N/N-1/N-2 정책)

[환경 변수]
  - VACUUM_SCHEDULE_CRON   [str, 기본값: "0 2 * * *"]  — 정기 VACUUM cron 표현식
  - VACUUM_BATCH_THRESHOLD [int, 기본값: 1000, 범위: 1~100_000] — 누적 삭제 임계값
  - PBKDF2_ITERATIONS      [int, 기본값: 600000, 범위: 100_000~10_000_000] — PBKDF2 반복 횟수
  - PBKDF2_HASH_NAME       [str, 기본값: "sha256"] — PBKDF2 해시 알고리즘
  - PBKDF2_KEY_LENGTH_BYTES [int, 기본값: 32, 범위: 16~64] — 파생 키 바이트 길이
  - PBKDF2_SALT_LENGTH_BYTES [int, 기본값: 32, 범위: 16~64] — 랜덤 솔트 바이트 길이

[주요 참조처 (Consumers)]
  - backend.api 또는 Celery 태스크: delete_user_data(), anonymize_log_entry() 호출
  - backend.core.audit_logger: 감사 이벤트 기록
  - backend.core.aws_client_wrapper: KMS/SSM에서 Global Pepper 페치
  - backend.services.personalized_index_service: FAISS 인덱스 제거
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import logging
import os
import secrets
from collections.abc import Awaitable, Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.audit_logger import AuditEventType, mask_uid, write_audit_log
from backend.core.aws_client_wrapper import fetch_global_pepper
from backend.services.personalized_index_service import (
    build_index_path,
    delete_index_metadata,
    load_index_metadata,
    should_rebuild_index,
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

# =============================================================================
# PBKDF2 익명화 파라미터 (환경 변수 우선, NIST SP 800-132 준수)
# =============================================================================

# 반복 횟수: NIST 권장 최솟값 이상 강제
_PBKDF2_ITERATIONS_ENV_KEY = "PBKDF2_ITERATIONS"
_DEFAULT_PBKDF2_ITERATIONS = 600_000
_MIN_PBKDF2_ITERATIONS = 100_000  # NIST SP 800-132 최솟값 기준 하한
_MAX_PBKDF2_ITERATIONS = 10_000_000

# 해시 알고리즘
_PBKDF2_HASH_NAME_ENV_KEY = "PBKDF2_HASH_NAME"
_DEFAULT_PBKDF2_HASH_NAME = "sha256"
_VALID_PBKDF2_HASH_NAMES = frozenset({"sha256", "sha384", "sha512"})

# 파생 키 바이트 길이 (최소 16바이트 = 128비트 — NIST 엔트로피 요건)
_PBKDF2_KEY_LENGTH_ENV_KEY = "PBKDF2_KEY_LENGTH_BYTES"
_DEFAULT_PBKDF2_KEY_LENGTH = 32
_MIN_PBKDF2_KEY_LENGTH = 16
_MAX_PBKDF2_KEY_LENGTH = 64

# 솔트 바이트 길이 (최소 16바이트 — NIST SP 800-132 §5.1)
_PBKDF2_SALT_LENGTH_ENV_KEY = "PBKDF2_SALT_LENGTH_BYTES"
_DEFAULT_PBKDF2_SALT_LENGTH = 32
_MIN_PBKDF2_SALT_LENGTH = 16
_MAX_PBKDF2_SALT_LENGTH = 64

# 키 로테이션 버전 (N: 현재, N-1: 과도기, N-2 이하: 폐기 대상)
_KEY_VERSION_ENV_KEY = "PBKDF2_KEY_VERSION"
_DEFAULT_KEY_VERSION = 1
_KEY_VERSION_TRANSITION_MAX_OFFSET = 1  # N-1 까지만 과도기 허용
_KEY_VERSION_DORMANT_THRESHOLD_OFFSET = 2  # N-2 이하 = 폐기·휴면 대상


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
# 결과 타입 정의 (Dataclass)
# =============================================================================


@dataclass(frozen=True)
class DeletionResult(Mapping[str, Any]):
    """
    delete_user_data() 반환값의 타입 계약.
    frozen=True를 통해 불변성(Immutability)을 보장하며,
    파생 필드(db_deleted)는 @property로 안전하게 제공됩니다.
    """

    masked_user_id: str  # 마스킹된 UID (masked_uid, 원문 PII 미사용)
    hashed_user_id: (
        str  # [DEPRECATED] 이전 API 호환성을 위해 유지 (masked_user_id와 동일)
    )
    db_rows_deleted: int  # DB 레코드 실제 삭제 행 수
    faiss_file_removed: bool  # FAISS 인덱스 파일 물리 삭제 성공 여부
    redis_meta_deleted: bool  # Redis 메타데이터 삭제 성공 여부
    compaction_recommended: bool  # FAISS Compaction 권장 여부
    vacuum_triggered: bool  # VACUUM 즉시 실행 권장 여부
    success: bool  # FAISS 파일 + Redis 메타 삭제 전체 성공 여부 (DB 0행은 멱등 성공으로 허용)

    @property
    def db_deleted(self) -> bool:
        """DB 레코드가 1건 이상 삭제되었는지 여부 (명시적 파생 필드)"""
        return self.db_rows_deleted > 0

    @classmethod
    def _extra_allowed_keys(cls) -> tuple[str, ...]:
        """서브클래스에서 노출할 추가 파생 필드(property)를 정의하는 확장 훅."""
        return ("db_deleted",)

    @classmethod
    @functools.lru_cache(maxsize=None)
    def _allowed_keys(cls) -> tuple[str, ...]:
        """데이터클래스 필드와 추가 허용 필드(훅)를 결합하여 캐싱합니다."""
        return (
            tuple(f.name for f in dataclasses.fields(cls)) + cls._extra_allowed_keys()
        )

    @classmethod
    @functools.lru_cache(maxsize=None)
    def _allowed_key_set(cls) -> frozenset[str]:
        return frozenset(cls._allowed_keys())

    # --- Mapping Protocol Implementation ---

    def __getitem__(self, key: str) -> Any:
        """기존 TypedDict 기반의 외부 호출부 하위 호환성을 위한 Mapping 인터페이스."""
        if key not in self.__class__._allowed_key_set():
            raise KeyError(key)
        return getattr(self, key)

    def __iter__(self) -> Iterator[str]:
        """dict() 형변환 및 Mapping 타입 반복문 지원을 위한 인터페이스."""
        return iter(self.__class__._allowed_keys())

    def __len__(self) -> int:
        """Mapping 프로토콜 완성을 위한 데이터 길이 반환."""
        return len(self.__class__._allowed_keys())

    @classmethod
    def create(
        cls,
        masked_uid: str,
        db_rows_deleted: int,
        faiss_removed: bool,
        redis_meta_deleted: bool,
        compaction_recommended: bool,
        vacuum_needed: bool,
    ) -> DeletionResult:
        """파이프라인 상태를 캡슐화하여 일관된 인스턴스를 생성하는 팩토리 메서드."""
        # success는 faiss_removed와 redis_meta_deleted의 조합으로 안전하게 자동 파생
        success = faiss_removed and redis_meta_deleted
        return cls(
            masked_user_id=masked_uid,
            hashed_user_id=masked_uid,
            db_rows_deleted=db_rows_deleted,
            faiss_file_removed=faiss_removed,
            redis_meta_deleted=redis_meta_deleted,
            compaction_recommended=compaction_recommended,
            vacuum_triggered=vacuum_needed,
            success=success,
        )


# =============================================================================
# 공개 API
# =============================================================================

__all__ = [
    "DeletionResult",
    "AnonymizationResult",
    "KeyRotationPolicy",
    "delete_user_data",
    "anonymize_log_entry",
    "get_current_key_version",
    "get_dormant_key_versions",
    "trigger_vacuum_if_needed",
    "get_vacuum_schedule_cron",
    "get_vacuum_batch_threshold",
    "get_pbkdf2_iterations",
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


# =============================================================================
# PBKDF2 익명화 파라미터 런타임 엑세서
# =============================================================================


def get_pbkdf2_iterations() -> int:
    """PBKDF2_ITERATIONS 환경 변수를 파싱하여 반환합니다 (NIST 범위 강제)."""
    raw = os.getenv(_PBKDF2_ITERATIONS_ENV_KEY)
    default = _DEFAULT_PBKDF2_ITERATIONS
    if raw is None:
        return default
    try:
        value = int(raw)
        if not (_MIN_PBKDF2_ITERATIONS <= value <= _MAX_PBKDF2_ITERATIONS):
            logger.warning(
                "[OBS][PRIVACY][CONFIG] '%s'=%d is outside NIST range [%d, %d]. "
                "Falling back to default %d.",
                _PBKDF2_ITERATIONS_ENV_KEY,
                value,
                _MIN_PBKDF2_ITERATIONS,
                _MAX_PBKDF2_ITERATIONS,
                default,
            )
            return default
        return value
    except (ValueError, TypeError):
        logger.warning(
            "[OBS][PRIVACY][CONFIG] '%s'=%r is not a valid integer. Falling back to default %d.",
            _PBKDF2_ITERATIONS_ENV_KEY,
            raw,
            default,
        )
        return default


def _get_pbkdf2_hash_name() -> str:
    """PBKDF2_HASH_NAME 환경 변수를 파싱하여 반환합니다 (유효값 검증 포함)."""
    raw = os.getenv(_PBKDF2_HASH_NAME_ENV_KEY, "").strip().lower()
    if raw not in _VALID_PBKDF2_HASH_NAMES:
        if raw:
            logger.warning(
                "[OBS][PRIVACY][CONFIG] '%s'=%r is not a valid hash name (valid: %s). "
                "Falling back to default '%s'.",
                _PBKDF2_HASH_NAME_ENV_KEY,
                raw,
                sorted(_VALID_PBKDF2_HASH_NAMES),
                _DEFAULT_PBKDF2_HASH_NAME,
            )
        return _DEFAULT_PBKDF2_HASH_NAME
    return raw


def _get_pbkdf2_int_param(
    env_key: str, default: int, min_val: int, max_val: int, param_label: str
) -> int:
    """공통 int 환경 변수 파라미터 파서 (범위 검증 + 폴백)."""
    raw = os.getenv(env_key)
    if raw is None:
        return default
    try:
        value = int(raw)
        if not (min_val <= value <= max_val):
            logger.warning(
                "[OBS][PRIVACY][CONFIG] '%s' (%s)=%d is outside range [%d, %d]. Falling back to %d.",
                env_key,
                param_label,
                value,
                min_val,
                max_val,
                default,
            )
            return default
        return value
    except (ValueError, TypeError):
        logger.warning(
            "[OBS][PRIVACY][CONFIG] '%s' (%s)=%r is not a valid integer. Falling back to %d.",
            env_key,
            param_label,
            raw,
            default,
        )
        return default


def get_current_key_version() -> int:
    """PBKDF2_KEY_VERSION 환경 변수를 반환합니다 (미설정 시 기본값 1)."""
    raw = os.getenv(_KEY_VERSION_ENV_KEY)
    if raw is None:
        return _DEFAULT_KEY_VERSION
    try:
        v = int(raw)
        return v if v >= 1 else _DEFAULT_KEY_VERSION
    except (ValueError, TypeError):
        return _DEFAULT_KEY_VERSION


def get_dormant_key_versions() -> list[int]:
    """
    현재 키 버전(N) 기준으로 N-2 이하의 폐기·휴면 버전 목록을 반환합니다.

    반환값이 비어 있지 않다면, 호출자(스케줄러)는 해당 버전의 휴면 데이터를 일괄 삭제해야 합니다.
    """
    current = get_current_key_version()
    dormant_start = current - _KEY_VERSION_DORMANT_THRESHOLD_OFFSET
    return list(range(1, max(0, dormant_start) + 1)) if dormant_start >= 1 else []


# =============================================================================
# NIST SP 800-132 런타임 준수 검증
# =============================================================================


def _validate_nist_pbkdf2_params(
    iterations: int,
    key_length: int,
    salt_length: int,
    hash_name: str,
) -> None:
    """
    PBKDF2 파라미터가 NIST SP 800-132 최소 요건을 충족하는지 런타임에 검증합니다.

    [검증 항목]
      - 반복 횟수: 100,000 이상 (NIST 권장 하한)
      - 파생 키 길이: 16바이트 이상 (128비트 엔트로피)
      - 솔트 길이: 16바이트 이상 (§5.1)
      - 해시 알고리즘: hashlib이 지원하는 유효한 알고리즘

    Raises:
        ValueError: 어느 하나의 파라미터라도 최소 요건을 미충족하는 경우
    """
    errors: list[str] = []

    if iterations < _MIN_PBKDF2_ITERATIONS:
        errors.append(
            f"iterations={iterations} < NIST minimum {_MIN_PBKDF2_ITERATIONS}"
        )
    if key_length < _MIN_PBKDF2_KEY_LENGTH:
        errors.append(
            f"key_length={key_length} bytes < minimum {_MIN_PBKDF2_KEY_LENGTH} bytes (128-bit)"
        )
    if salt_length < _MIN_PBKDF2_SALT_LENGTH:
        errors.append(
            f"salt_length={salt_length} bytes < NIST SP 800-132 §5.1 minimum {_MIN_PBKDF2_SALT_LENGTH} bytes"
        )
    try:
        hashlib.new(hash_name)
    except ValueError:
        errors.append(f"hash_name='{hash_name}' is not supported by hashlib")

    if errors:
        raise ValueError(
            "[PRIVACY] NIST SP 800-132 PBKDF2 parameter validation failed: "
            + "; ".join(errors)
        )


# =============================================================================
# 익명화 결과 타입 및 키 로테이션 정책
# =============================================================================


class KeyRotationPolicy(str, Enum):
    """
    키 버전 상태 분류.
      CURRENT    : N  (현재 활성 키)
      TRANSITION : N-1 (과도기 — 최대 1년 보관)
      DORMANT    : N-2 이하 (폐기 대상 — 스케줄러가 일괄 삭제)
    """

    CURRENT = "current"
    TRANSITION = "transition"
    DORMANT = "dormant"


@dataclass(frozen=True)
class Pbkdf2Config:
    """
    PBKDF2 익명화에 필요한 파라미터를 캡슐화한 불변 설정 객체.
    NIST SP 800-132 검증이 완료된 상태임을 보장합니다.
    """

    iterations: int
    hash_name: str
    key_length: int
    salt_length: int
    key_version: int


@dataclass(frozen=True)
class AnonymizationResult:
    """
    anonymize_log_entry() 반환값의 타입 계약.
    모든 필드는 불변이며 PII 원문을 포함하지 않습니다.
    """

    masked_user_id: str  # 마스킹된 UID (PII 미포함)
    anonymized_value: str  # hex 인코딩된 PBKDF2 파생 값
    salt_hex: str  # 검증용 hex 인코딩 솔트 (재연산 불필요 — 감사용)
    key_version: int  # 사용된 키 버전
    key_rotation_policy: KeyRotationPolicy  # 해당 버전의 로테이션 정책
    iterations: int  # 사용된 반복 횟수 (NIST 준수 감사)
    hash_name: str  # 사용된 해시 알고리즘
    success: bool  # 익명화 성공 여부


# =============================================================================
# 익명화 내부 헬퍼 (순수 함수 — 테스트 용이성 확보)
# =============================================================================


def _load_pbkdf2_config() -> Pbkdf2Config:
    """
    환경 변수에서 PBKDF2 파라미터를 로드하고 NIST SP 800-132 검증을 수행한 뒤
    캡슐화된 설정 객체를 반환합니다.

    Raises:
        ValueError: NIST 최소 요건 미충족 시
    """
    iterations = get_pbkdf2_iterations()
    hash_name = _get_pbkdf2_hash_name()
    key_length = _get_pbkdf2_int_param(
        _PBKDF2_KEY_LENGTH_ENV_KEY,
        _DEFAULT_PBKDF2_KEY_LENGTH,
        _MIN_PBKDF2_KEY_LENGTH,
        _MAX_PBKDF2_KEY_LENGTH,
        "key_length",
    )
    salt_length = _get_pbkdf2_int_param(
        _PBKDF2_SALT_LENGTH_ENV_KEY,
        _DEFAULT_PBKDF2_SALT_LENGTH,
        _MIN_PBKDF2_SALT_LENGTH,
        _MAX_PBKDF2_SALT_LENGTH,
        "salt_length",
    )
    key_version = get_current_key_version()

    # NIST 검증 — 실패 시 ValueError 발생 → 파이프라인 진입 불가
    _validate_nist_pbkdf2_params(iterations, key_length, salt_length, hash_name)

    return Pbkdf2Config(
        iterations=iterations,
        hash_name=hash_name,
        key_length=key_length,
        salt_length=salt_length,
        key_version=key_version,
    )


def _compute_rotation_policy(
    current_version: int, data_version: int
) -> KeyRotationPolicy:
    """
    현재 시스템 키 버전(current_version)과 데이터의 키 버전(data_version)을 비교하여
    로테이션 상태를 분류합니다.

    [분류 기준]
      DORMANT    : data_version <= current_version - 2 (N-2 이하)
      TRANSITION : data_version == current_version - 1 (N-1)
      CURRENT    : data_version == current_version      (N)
    """
    if data_version <= current_version - _KEY_VERSION_DORMANT_THRESHOLD_OFFSET:
        return KeyRotationPolicy.DORMANT
    if data_version == current_version - _KEY_VERSION_TRANSITION_MAX_OFFSET:
        return KeyRotationPolicy.TRANSITION
    return KeyRotationPolicy.CURRENT


def _derive_anonymized_value(
    value: str,
    pepper: str,
    config: Pbkdf2Config,
) -> tuple[str, str]:
    """
    PBKDF2-HMAC 파생 연산을 수행하는 순수 함수.
    I/O 없이 오직 암호학적 연산만 담당합니다.

    [보안]
      - pepper는 반환값이나 로그에 포함되지 않습니다 (PII/비밀 데이터)
      - salt는 암호학적으로 안전한 secrets.token_bytes()로 생성

    Returns:
        (anonymized_hex, salt_hex) 튜플
    """
    salt: bytes = secrets.token_bytes(config.salt_length)
    # password = value + pepper 조합으로 엔트로피 최대화
    password_bytes: bytes = (value + pepper).encode("utf-8")
    derived_key: bytes = hashlib.pbkdf2_hmac(
        hash_name=config.hash_name,
        password=password_bytes,
        salt=salt,
        iterations=config.iterations,
        dklen=config.key_length,
    )
    return derived_key.hex(), salt.hex()


# =============================================================================
# 익명화 파이프라인
# =============================================================================


async def anonymize_log_entry(
    hashed_user_id: str,
    log_field_value: str,
) -> AnonymizationResult:
    """
    Interaction Log의 단일 필드 값을 PBKDF2-HMAC-SHA256으로 안전하게 익명화합니다.

    [보안 설계]
      - Global Pepper: KMS/SSM에서 런타임 메모리 주입 (aws_client_wrapper 재사용)
      - Per-Entry Salt: secrets.token_bytes()로 암호학적으로 안전한 랜덤 솔트 생성
      - NIST SP 800-132 준수: _load_pbkdf2_config() 내에서 파라미터 검증 후 진행

    [키 로테이션]
      - PBKDF2_KEY_VERSION 환경 변수로 현재 시스템 키 버전(N)을 관리
      - N-1 버전 데이터는 과도기(TRANSITION) 처리 — 최대 1년 보관
      - N-2 이하 버전 데이터는 휴면(DORMANT) — get_dormant_key_versions()로 스케줄러에 통보

    [감사 로그 흐름]
      DATA_ANONYMIZE_STARTED → (성공) DATA_ANONYMIZE_SUCCESS
                             → (실패) DATA_ANONYMIZE_FAILURE
      rotation_policy는 extra 메타데이터로만 기록되며 이벤트 타입 결정에 사용되지 않습니다.

    Args:
        hashed_user_id: compute_hashed_user_id()의 반환값 (PII 미포함).
        log_field_value: 익명화할 로그 필드 원문 값.

    Returns:
        AnonymizationResult (불변 객체)

    Raises:
        ValueError: 입력값이 비어있거나 NIST 파라미터 검증 실패 시
    """
    if not hashed_user_id:
        raise ValueError("anonymize_log_entry: 'hashed_user_id' must not be empty.")
    if not log_field_value:
        raise ValueError("anonymize_log_entry: 'log_field_value' must not be empty.")

    masked = mask_uid(hashed_user_id)

    # ── 설정 로드 및 NIST 검증 (실패 시 즉시 ValueError — try 블록 진입 안 함) ──
    config: Pbkdf2Config = _load_pbkdf2_config()
    rotation_policy: KeyRotationPolicy = _compute_rotation_policy(
        current_version=config.key_version,
        data_version=config.key_version,
    )

    # ── 시작 이벤트 기록 (결과 미확정 — 중립적 STARTED 사용) ─────────────────
    write_audit_log(
        event_type=AuditEventType.DATA_ANONYMIZE_STARTED,
        masked_uid=masked,
        result="anonymization_initiated",
        extra={
            "key_version": config.key_version,
            "rotation_policy": rotation_policy.value,
        },
    )

    try:
        # ── Global Pepper 로드 (KMS/SSM 런타임 메모리 주입) ───────────────────
        pepper: str = await fetch_global_pepper()

        # ── 순수 PBKDF2 파생 연산 ─────────────────────────────────────────────
        anonymized_hex, salt_hex = _derive_anonymized_value(
            log_field_value, pepper, config
        )

        logger.info(
            "[OBS][PRIVACY] Log field anonymized: masked_uid=%s, key_version=%d, "
            "iterations=%d, hash=%s, rotation_policy=%s",
            masked,
            config.key_version,
            config.iterations,
            config.hash_name,
            rotation_policy.value,
        )
        write_audit_log(
            event_type=AuditEventType.DATA_ANONYMIZE_SUCCESS,
            masked_uid=masked,
            result="success",
            extra={
                "key_version": config.key_version,
                "rotation_policy": rotation_policy.value,
                "iterations": config.iterations,
                "hash_name": config.hash_name,
            },
        )

        return AnonymizationResult(
            masked_user_id=masked,
            anonymized_value=anonymized_hex,
            salt_hex=salt_hex,
            key_version=config.key_version,
            key_rotation_policy=rotation_policy,
            iterations=config.iterations,
            hash_name=config.hash_name,
            success=True,
        )

    except Exception as e:
        logger.exception(
            "[OBS][PRIVACY] Anonymization failed for masked_uid=%s: error_type=%s, error_msg=%s",
            masked,
            type(e).__name__,
            str(e),
        )
        write_audit_log(
            event_type=AuditEventType.DATA_ANONYMIZE_FAILURE,
            masked_uid=masked,
            result=f"anonymization_failed: {type(e).__name__}",
            extra={
                "key_version": config.key_version,
                "rotation_policy": rotation_policy.value,
            },
        )
        return AnonymizationResult(
            masked_user_id=masked,
            anonymized_value="",
            salt_hex="",
            key_version=config.key_version,
            key_rotation_policy=rotation_policy,
            iterations=config.iterations,
            hash_name=config.hash_name,
            success=False,
        )


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

    # 파이프라인 상태 변수 초기화
    db_rows_deleted = 0
    faiss_removed = False
    redis_meta_deleted = False
    compaction_recommended = False
    vacuum_needed = False

    # ── 1. DB 레코드 물리적 삭제 ──────────────────────────────────────────
    write_audit_log(
        event_type=AuditEventType.DATA_DELETE_REQUESTED,
        masked_uid=masked,
        result="initiated",
    )

    try:
        rows_deleted: int = await db_delete_fn(hashed_user_id)
        db_rows_deleted = rows_deleted
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
        return DeletionResult.create(
            masked_uid=masked,
            db_rows_deleted=db_rows_deleted,
            faiss_removed=faiss_removed,
            redis_meta_deleted=redis_meta_deleted,
            compaction_recommended=compaction_recommended,
            vacuum_needed=vacuum_needed,
        )

    # ── 2. 누적 카운터 및 VACUUM 트리거 판단 ──────────────────────────────
    current_count = _increment_deletion_counter()
    vacuum_needed = trigger_vacuum_if_needed(current_count)

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

    # ── 4. Redis 메타데이터 삭제 ──────────────────────────────────────────
    try:
        # 컴팩션 필요 여부를 삭제 전 메타데이터로 판단
        existing_meta = await load_index_metadata(hashed_user_id)
        if existing_meta is not None:
            compaction_recommended = should_rebuild_index(existing_meta)
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

    # ── 5. 최종 결과 판단 및 감사 로그 기록 ─────────────────────────
    # FAISS 파일 + Redis 메타 삭제가 모두 성공이면 `success=True`.
    # rows_deleted == 0인 경우에도 예외가 없다면(애초에 삭제할 데이터가 없었던 경우)
    # 멱등적 성공으로 처리합니다. DB 예외는 위에서 조기 리턴하므로 여기 도달 시 DB 단계는 무결합니다.
    # 모든 조건을 AND로 연결하여 조용한 실패를 구조적으로 탐지합니다.
    overall_success = faiss_removed and redis_meta_deleted

    if overall_success:
        is_idempotent = db_rows_deleted == 0
        write_audit_log(
            event_type=AuditEventType.DATA_DELETE_SUCCESS,
            masked_uid=masked,
            result="idempotent_success" if is_idempotent else "success",
            extra={
                "db_rows_deleted": db_rows_deleted,
                "faiss_file_removed": faiss_removed,
                "redis_meta_deleted": redis_meta_deleted,
                "compaction_recommended": compaction_recommended,
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

    # ── 최종 불변 객체(Dataclass) 생성 및 반환 ──
    return DeletionResult.create(
        masked_uid=masked,
        db_rows_deleted=db_rows_deleted,
        faiss_removed=faiss_removed,
        redis_meta_deleted=redis_meta_deleted,
        compaction_recommended=compaction_recommended,
        vacuum_needed=vacuum_needed,
    )

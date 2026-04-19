# backend/services/personalized_index_service.py

"""
[Step 2 - Phase 2] 사용자별 결정론적 FAISS 서브-인덱스 경로 생성 및 메타데이터 관리
======================================================================================

설계 원칙 (개인정보 보호 우선):
  - user_id는 절대 파일 시스템, Redis 키, 로그에 평문으로 기록하지 않는다.
  - 파일 경로 생성에는 SHA-256(user_id + per_user_salt + global_pepper) 해시만 사용한다.
  - global_pepper는 AWS KMS(SSM Parameter Store)를 통해 런타임 메모리에만 주입된다.
  - 로그에 user_id를 출력해야 하는 경우 반드시 mask_pii_id() 헬퍼를 사용한다.

Redis 스키마:
  - Key   : "prs_idx:meta:{hashed_user_id}"   (Hash)
  - Fields: created_at, updated_at, vector_count, index_path

Path 전략:
  - {STORAGE_BASE_PATH}/user_data/idx/{hashed_user_id}.faiss
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import os
import types
import typing
import redis.asyncio as redis_async
import redis.exceptions
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.core.aws_client_wrapper import fetch_global_pepper  # type: ignore[import]
from backend.core.config_validator import PersonalizedRAGConfig   # type: ignore[import]
from backend.services.redis_pubsub import redis_client            # type: ignore[import]
from backend.utils import mask_pii_id                             # type: ignore[import]

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 모듈 레벨 상수 (하드코딩 금지 — 모두 여기서 중앙 관리)
# ─────────────────────────────────────────────────────────────────────────────

# Redis 키 접두사 — 변경 시 이 상수 하나만 수정하면 전체 반영
_REDIS_META_PREFIX: str = "prs_idx:meta"

# 인덱스 파일이 위치할 서브디렉토리 경로 조각 (STORAGE_BASE_PATH 하위)
_INDEX_SUBDIR: str = "user_data/idx"

# 해시 알고리즘 식별자 — 변경 시 이 상수 하나만 수정
_HASH_ALGORITHM: str = "sha256"

# Redis 메타데이터 TTL (초): 환경 변수 PERSONALIZED_INDEX_META_TTL로 오버라이드 가능
# 기본값 30일 = 2,592,000초 (운영 환경에서 충분한 캐시 보존)
_DEFAULT_META_TTL_SECS: int = 2_592_000
_META_TTL_MIN_SECS: int = 3_600       # 최소 1시간
_META_TTL_MAX_SECS: int = 31_536_000  # 최대 1년

# 스키마 파싱 경고 로그 레벨
# 기본값: WARNING (일반 운영)
# 마이그레이션 중 다량의 구(old) 레코드 처리 시 INFO로 낮춰 APM 노이즈를 억제할 수 있음:
#   PERSONALIZED_INDEX_SCHEMA_LOG_LEVEL=INFO
_SCHEMA_LOG_LEVEL_MAP: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}
_DEFAULT_SCHEMA_LOG_LEVEL: int = logging.WARNING


def _load_schema_log_level() -> int:
    """
    PERSONALIZED_INDEX_SCHEMA_LOG_LEVEL 환경 변수를 파싱하여 로그 레벨 int를 반환한다.

    - 미설정: 기본값 WARNING 사용
    - 알 수 없는 레벨명: WARNING 로그 후 기본값으로 폴백

    허용 값: DEBUG, INFO, WARNING, ERROR (대소문자 무시)
    """
    raw = os.environ.get("PERSONALIZED_INDEX_SCHEMA_LOG_LEVEL", "").strip().upper()
    if not raw:
        return _DEFAULT_SCHEMA_LOG_LEVEL

    level = _SCHEMA_LOG_LEVEL_MAP.get(raw)
    if level is None:
        logger.warning(
            "[PERSONALIZED_INDEX][CONFIG] 'PERSONALIZED_INDEX_SCHEMA_LOG_LEVEL'=%r is "
            "not a valid log level (allowed: %s); falling back to WARNING.",
            raw,
            list(_SCHEMA_LOG_LEVEL_MAP.keys()),
        )
        return _DEFAULT_SCHEMA_LOG_LEVEL

    return level


# 모듈 로드 시 1회 파싱 (운영 중 환경변수 변경은 재시작 필요)
_SCHEMA_LOG_LEVEL: int = _load_schema_log_level()


def _load_meta_ttl() -> int:
    """
    PERSONALIZED_INDEX_META_TTL 환경 변수를 파싱하여 TTL(초)를 반환한다.
    - 미설정: 기본값(_DEFAULT_META_TTL_SECS) 사용
    - 비정수 또는 범위 초과: WARNING 로그 후 기본값으로 폴백 (Silent Failure 금지)
    """
    raw = os.environ.get("PERSONALIZED_INDEX_META_TTL")
    if raw is None:
        return _DEFAULT_META_TTL_SECS

    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[PERSONALIZED_INDEX][CONFIG] 'PERSONALIZED_INDEX_META_TTL'=%r is not a valid "
            "integer; falling back to default %d seconds.",
            raw,
            _DEFAULT_META_TTL_SECS,
        )
        return _DEFAULT_META_TTL_SECS

    if not (_META_TTL_MIN_SECS <= value <= _META_TTL_MAX_SECS):
        clamped = max(_META_TTL_MIN_SECS, min(_META_TTL_MAX_SECS, value))
        logger.warning(
            "[PERSONALIZED_INDEX][CONFIG] 'PERSONALIZED_INDEX_META_TTL'=%d is outside "
            "valid range [%d, %d]; clamped to %d.",
            value,
            _META_TTL_MIN_SECS,
            _META_TTL_MAX_SECS,
            clamped,
        )
        return clamped

    return value


# 컴팩션(재빌드) 임계값 설정
# - FAISS_COMPACTION_VECTOR_THRESHOLD: 벡터 개수 기반 (기본 500, 최소 100)
# - FAISS_COMPACTION_DELETE_RATIO: 삭제 비율 기반 (기본 0.15, 범위 0.0~1.0)
_DEFAULT_COMPACTION_THRESHOLD: int = 500
_MIN_COMPACTION_THRESHOLD: int = 100

_DEFAULT_DELETE_RATIO: float = 0.15
_DELETE_RATIO_MIN: float = 0.0
_DELETE_RATIO_MAX: float = 1.0

# 삭제 비율 기반 컴팩션에서 노이즈 트리거를 방지하기 위한 최소 데이터셋 규모
_MIN_DATASET_SIZE_FOR_COMPACTION: int = 10


def _load_compaction_threshold() -> int:
    """FAISS_COMPACTION_VECTOR_THRESHOLD 환경 변수를 로드하고 보정(Clamp)한다."""
    raw = os.environ.get("FAISS_COMPACTION_VECTOR_THRESHOLD")
    if raw is None:
        return _DEFAULT_COMPACTION_THRESHOLD
    try:
        val = int(raw)
        if val < _MIN_COMPACTION_THRESHOLD:
            logger.warning(
                "[PERSONALIZED_INDEX][CONFIG] 'FAISS_COMPACTION_VECTOR_THRESHOLD'=%d is "
                "below minimum %d; clamped to %d.",
                val, _MIN_COMPACTION_THRESHOLD, _MIN_COMPACTION_THRESHOLD
            )
            return _MIN_COMPACTION_THRESHOLD
        return val
    except (ValueError, TypeError):
        logger.warning(
            "[PERSONALIZED_INDEX][CONFIG] 'FAISS_COMPACTION_VECTOR_THRESHOLD'=%r is "
            "not a valid integer; falling back to %d.",
            raw, _DEFAULT_COMPACTION_THRESHOLD
        )
        return _DEFAULT_COMPACTION_THRESHOLD


def _load_delete_ratio() -> float:
    """FAISS_COMPACTION_DELETE_RATIO 환경 변수를 로드하고 범위 내로 보정한다."""
    raw = os.environ.get("FAISS_COMPACTION_DELETE_RATIO")
    if raw is None:
        return _DEFAULT_DELETE_RATIO
    try:
        val = float(raw)
        if not (_DELETE_RATIO_MIN <= val <= _DELETE_RATIO_MAX):
            clamped = max(_DELETE_RATIO_MIN, min(_DELETE_RATIO_MAX, val))
            logger.warning(
                "[PERSONALIZED_INDEX][CONFIG] 'FAISS_COMPACTION_DELETE_RATIO'=%f is "
                "outside range [%.1f, %.1f]; clamped to %.2f.",
                val, _DELETE_RATIO_MIN, _DELETE_RATIO_MAX, clamped
            )
            return clamped
        return val
    except (ValueError, TypeError):
        logger.warning(
            "[PERSONALIZED_INDEX][CONFIG] 'FAISS_COMPACTION_DELETE_RATIO'=%r is "
            "not a valid float; falling back to %.2f.",
            raw, _DEFAULT_DELETE_RATIO
        )
        return _DEFAULT_DELETE_RATIO


# 모듈 로드 시 1회 파싱
_META_TTL_SECS: int = _load_meta_ttl()
_COMPACTION_THRESHOLD: int = _load_compaction_threshold()
_DELETE_RATIO_THRESHOLD: float = _load_delete_ratio()

# 메타데이터 원자적 갱신을 위한 Lua 스크립트 (모듈 레벨 컴파일로 파싱 비용 절감)
# - KEYS[1]: Redis Hash Key
# - ARGV[1]: vector_delta (추가/삭제 수)
# - ARGV[2]: delete_delta (무효화 수)
# - ARGV[3]: updated_at (ISO 시간 문자열)
# - ARGV[4]: _META_TTL_SECS
_LUA_UPDATE_META_SCRIPT: str = """
if redis.call("EXISTS", KEYS[1]) == 0 then
    return nil
end
local v = tonumber(redis.call("HGET", KEYS[1], "vector_count") or "0")
local d = tonumber(redis.call("HGET", KEYS[1], "deleted_count") or "0")

v = math.max(0, v + tonumber(ARGV[1]))
d = math.max(0, d + tonumber(ARGV[2]))

redis.call("HSET", KEYS[1], "vector_count", tostring(v), "deleted_count", tostring(d), "updated_at", ARGV[3])
redis.call("EXPIRE", KEYS[1], tonumber(ARGV[4]))

return redis.call("HGETALL", KEYS[1])
"""



# ─────────────────────────────────────────────────────────────────────────────
# 데이터 클래스: Redis에 저장할 인덱스 메타데이터 스키마
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class IndexMetadata:
    """
    Redis Hash에 저장되는 FAISS 서브-인덱스 메타데이터.

    Fields:
        created_at   : 인덱스 최초 생성 ISO 8601 UTC 타임스탬프
        updated_at   : 마지막 업데이트 ISO 8601 UTC 타임스탬프
        vector_count : 현재 저장된 유효 벡터 수 (전체 벡터 - 삭제된 벡터)
        deleted_count: 논리적으로 삭제된 벡터 수 (컴팩션 시 실제 제거 대상)
        index_path   : 파일 시스템 상의 .faiss 파일 절대 경로
                       (hashed_user_id 기반이므로 PII 미포함)

    설계 원칙:
        - 필드에 기본값을 부여하여 Redis 스키마 마이그레이션 중 구(old) 레코드와
          신(new) 스키마가 공존할 때 서비스 장애를 방지한다 (Graceful Degradation).
        - index_path가 Redis에 없더라도 hashed_user_id + cfg로 재계산 가능하므로
          빈 문자열을 기본값으로 허용하고 호출자가 필요 시 재보정한다.
    """

    created_at: str = ""
    updated_at: str = ""
    vector_count: int = 0
    deleted_count: int = 0  # 신규: 인덱스 내 삭제된(무효화된) 벡터 수
    index_path: str = ""

    def to_redis_dict(self) -> dict[str, str]:
        """Redis hset에 전달할 string dict 반환."""
        return {
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "vector_count": str(self.vector_count),
            "deleted_count": str(self.deleted_count),
            "index_path": self.index_path,
        }

    @classmethod
    def from_redis_dict(cls, raw: dict[bytes | str, bytes | str]) -> "IndexMetadata":
        """
        Redis hgetall 결과(bytes or str 키/값)를 IndexMetadata로 관대하게 변환한다.

        처리 원칙:
          1. 모든 키·값을 str로 1회 정규화 — decode_responses 설정 무관 안전 동작.
          2. 필드 목록·기본값·타입을 dataclasses.fields(cls)와 get_type_hints(cls)에서
             동적으로 파생 — 하드코딩 금지 (완전한 SSOT).
          3. 기본값 없는 필수 필드(MISSING)가 Redis에도 없으면 즉시 ValueError — Fail-fast.
             (현재 IndexMetadata는 모든 필드에 기본값이 있어 이 경로는 미래 대비 방어)
          4. 필드 누락 시 dataclass 기본값으로 폴백, _SCHEMA_LOG_LEVEL 레벨로 로그.
             → 마이그레이션 중 INFO로 낮춰 APM 노이즈 억제 가능.
          5. per-type 디스패처로 str/int/float/bool 타입 각각 안전하게 변환.
             미지원 타입은 WARNING 로그 후 raw str 사용.
        """
        def _to_str(v: bytes | str) -> str:
            return v.decode("utf-8") if isinstance(v, bytes) else str(v)

        # 1회 정규화: 이후 코드는 str key/value만 사용 — KeyError 교차 발생 원천 차단
        normalized: dict[str, str] = {_to_str(k): _to_str(v) for k, v in raw.items()}

        # 필드 메타데이터를 데이터클래스 정의에서 동적 파생 (완전한 SSOT)
        cls_fields = dataclasses.fields(cls)
        type_hints: dict[str, type] = typing.get_type_hints(cls)

        def _get_field_default(f: dataclasses.Field) -> object:
            """
            dataclasses.Field에서 실제 기본값을 반환한다.
            기본값이 없으면 dataclasses.MISSING 을 반환한다.
            """
            if f.default is not dataclasses.MISSING:
                return f.default
            if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
                return f.default_factory()  # type: ignore[misc]
            return dataclasses.MISSING

        field_defaults: dict[str, object] = {f.name: _get_field_default(f) for f in cls_fields}

        # 누락 필드 감지: dataclass 기본값으로 폴백 (MISSING이 아닌 경우) + _SCHEMA_LOG_LEVEL 레벨 로그
        missing = [name for name in field_defaults if name not in normalized and field_defaults[name] is not dataclasses.MISSING]
        if missing:
            logger.log(
                _SCHEMA_LOG_LEVEL,
                "[PERSONALIZED_INDEX][SCHEMA] from_redis_dict: missing fields %s — "
                "falling back to dataclass defaults. Redis hash may be from an older schema version. "
                "(Adjust 'PERSONALIZED_INDEX_SCHEMA_LOG_LEVEL' env var to suppress during migration.)",
                missing,
            )

        def _parse_value(field_name: str, raw_val: str, field_type: type, default: object) -> object:
            """
            Redis raw str 값을 필드의 실제 Python 타입으로 안전하게 변환한다.
            지원 타입: str, int, float, bool
            미지원 타입: WARNING 로그 후 raw str 반환 (서비스 장애 전파 방지)
            """
            origin = typing.get_origin(field_type)  # Optional, Union (typing / PEP 604) 등의 원본 타입
            
            # Union 처리 (typing.Union 또는 types.UnionType)
            union_types = (typing.Union, getattr(types, "UnionType", ()))
            if origin in union_types:
                args = [a for a in typing.get_args(field_type) if a is not type(None)]
                if len(args) > 1:
                    raise TypeError(
                        f"[PERSONALIZED_INDEX][SCHEMA] Field '{field_name}' uses a multi-type Union: {field_type}. "
                        f"from_redis_dict does not support converting abstract multiple types. "
                        f"Please use a single concrete type or Optional[T]."
                    )
                field_type = args[0] if args else str

            if field_type is str:
                return raw_val
            if field_type is int:
                try:
                    return int(raw_val)
                except (ValueError, TypeError):
                    logger.log(
                        _SCHEMA_LOG_LEVEL,
                        "[PERSONALIZED_INDEX][SCHEMA] from_redis_dict: field '%s'=%r "
                        "cannot be parsed as int; falling back to dataclass default. "
                        "(Adjust 'PERSONALIZED_INDEX_SCHEMA_LOG_LEVEL' env var to suppress.)",
                        field_name, raw_val,
                    )
                    return default
            if field_type is float:
                try:
                    return float(raw_val)
                except (ValueError, TypeError):
                    logger.log(
                        _SCHEMA_LOG_LEVEL,
                        "[PERSONALIZED_INDEX][SCHEMA] from_redis_dict: field '%s'=%r "
                        "cannot be parsed as float; falling back to dataclass default.",
                        field_name, raw_val,
                    )
                    return default
            if field_type is bool:
                # Redis에 "True"/"False"/"1"/"0" 형태로 저장될 수 있음
                return raw_val.lower() in ("true", "1", "yes")

            # 미지원 타입: 안전하게 raw str 반환하고 운영자에게 알림
            logger.warning(
                "[PERSONALIZED_INDEX][SCHEMA] from_redis_dict: field '%s' has unsupported "
                "type '%s' for automatic conversion; returning raw string. "
                "Add a type handler to _parse_value() to suppress this warning.",
                field_name, field_type,
            )
            return raw_val

        # per-type 디스패처로 모든 필드를 타입에 맞게 안전하게 변환
        kwargs: dict[str, object] = {}
        for f in cls_fields:
            field_type = type_hints.get(f.name, str)
            default = field_defaults[f.name]
            raw_val = normalized.get(f.name)
            if raw_val is None:
                # 필드가 Redis에 없는 경우
                if default is dataclasses.MISSING:
                    # Redis에도 데이터가 없고, dataclass에도 기본값이 없는 경우에만 fail-fast
                    raise ValueError(
                        f"[PERSONALIZED_INDEX][SCHEMA] IndexMetadata field '{f.name}' has no "
                        f"default value and was not supplied by Redis. Cannot instantiate."
                    )
                # dataclass 기본값 사용 (이미 missing 로그 처리됨)
                kwargs[f.name] = default
            else:
                kwargs[f.name] = _parse_value(f.name, raw_val, field_type, default)

        return cls(**kwargs)




# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼 함수
# ─────────────────────────────────────────────────────────────────────────────


def _build_meta_key(hashed_user_id: str) -> str:
    """
    Redis 메타데이터 Hash 키를 생성한다.
    모든 Redis 키는 반드시 이 함수를 통해 생성 — 하드코딩 금지.

    Returns:
        "prs_idx:meta:{hashed_user_id}"
    """
    return f"{_REDIS_META_PREFIX}:{hashed_user_id}"


def _extract_masked_uid_from_key(key: str) -> str:
    """
    Redis 메타데이터 키에서 유저 식별자(마스킹용 앞 8자리)를 역추출한다.
    의도치 않은 타입(None 등)이 전달된 경우 명시적(Explicit) 에러를 발생시키기 위해
    광범위한 예외 캐치를 수행하지 않습니다.
    """
    return key.rsplit(":", 1)[-1][:8]


def _now_utc_iso() -> str:
    """현재 UTC 시각을 ISO 8601 문자열로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


async def _ensure_redis_connected() -> None:
    """
    Redis 연결 상태를 확인하고, 미연결 시 연결을 시도하는 내부 헬퍼.

    각 비동기 함수마다 `if not redis_client.is_connected(): await redis_client.connect()`
    패턴이 중복되는 것을 방지하기 위해 이 헬퍼를 통해 연결 관리를 중앙집중화한다.
    연결 실패 시 예외를 상위로 전파한다.
    """
    if not redis_client.is_connected():
        await redis_client.connect()


# ─────────────────────────────────────────────────────────────────────────────
# 핵심 공개 함수
# ─────────────────────────────────────────────────────────────────────────────


def compute_hashed_user_id(
    user_id: str,
    per_user_salt: str,
    global_pepper: str,
) -> str:
    """
    SHA-256(user_id + per_user_salt + global_pepper) 기반의 결정론적 해시를 생성한다.

    보안 설계:
      - user_id    : 식별자 (PII 포함 가능)
      - per_user_salt: DB 레코드에 평문 저장 (고유성 목적)
      - global_pepper: KMS에서 메모리로만 주입 (역추적 방어)

    세 값을 단순 연결(concatenation)하면 길이 연장 공격(length-extension attack)에
    취약하므로, HMAC 없이 충분한 엔드로피를 확보하기 위해 '|' 구분자를 사용하여
    각 구성 요소가 명확히 분리되도록 한다.

    Args:
        user_id       : 사용자 식별자 (PII — 이 함수 외부로 절대 유출 금지)
        per_user_salt : DB에 저장된 사용자별 고유 솔트
        global_pepper : KMS에서 메모리로 주입된 글로벌 페퍼

    Returns:
        64자 16진수 문자열 (SHA-256 hex digest)

    Raises:
        ValueError: 입력 중 하나라도 빈 문자열인 경우
    """
    if not user_id:
        raise ValueError("compute_hashed_user_id: 'user_id' must not be empty.")
    if not per_user_salt:
        raise ValueError("compute_hashed_user_id: 'per_user_salt' must not be empty.")
    if not global_pepper:
        raise ValueError("compute_hashed_user_id: 'global_pepper' must not be empty.")

    # '|' 구분자로 각 구성 요소를 명확히 분리하여 prefix collision 방지
    raw_material = f"{user_id}|{per_user_salt}|{global_pepper}"
    digest = hashlib.new(_HASH_ALGORITHM, raw_material.encode("utf-8")).hexdigest()

    # PII 보호: user_id 자체는 절대 로그에 기록하지 않는다
    logger.debug(
        "[PERSONALIZED_INDEX] hashed_user_id computed (masked_uid=%s, algo=%s)",
        mask_pii_id(user_id),
        _HASH_ALGORITHM,
    )
    return digest


def build_index_path(hashed_user_id: str, storage_base_path: str) -> Path:
    """
    hashed_user_id와 STORAGE_BASE_PATH를 조합하여 결정론적 .faiss 파일 경로를 반환한다.

    경로 구조: {storage_base_path}/user_data/idx/{hashed_user_id}.faiss

    Args:
        hashed_user_id   : compute_hashed_user_id()의 반환값 (PII 미포함)
        storage_base_path: PersonalizedRAGConfig.storage_base_path (필수 환경변수)

    Returns:
        Path 객체 (파일 생성 전 디렉토리 존재 여부는 보장하지 않음)

    Raises:
        ValueError: hashed_user_id 또는 storage_base_path가 비어 있는 경우
    """
    if not hashed_user_id:
        raise ValueError("build_index_path: 'hashed_user_id' must not be empty.")
    if not storage_base_path:
        raise ValueError("build_index_path: 'storage_base_path' must not be empty.")

    index_path = Path(storage_base_path) / _INDEX_SUBDIR / f"{hashed_user_id}.faiss"

    logger.debug(
        "[PERSONALIZED_INDEX] index_path resolved (subdir=%s)",
        _INDEX_SUBDIR,
    )
    return index_path


def ensure_index_directory(index_path: Path) -> None:
    """
    인덱스 파일의 부모 디렉토리가 존재하지 않으면 생성한다.
    디렉토리 생성 권한이 없는 경우 PermissionError를 상위로 전파한다.

    Args:
        index_path: build_index_path()의 반환값
    """
    parent = index_path.parent
    if not parent.exists():
        logger.info(
            "[PERSONALIZED_INDEX] Creating index directory: %s",
            parent,
        )
        parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Redis 메타데이터 CRUD
# ─────────────────────────────────────────────────────────────────────────────


async def save_index_metadata(
    hashed_user_id: str,
    metadata: IndexMetadata,
) -> None:
    """
    FAISS 인덱스 메타데이터를 Redis Hash에 저장(upsert)한다.

    Redis Key: "prs_idx:meta:{hashed_user_id}"
    TTL      : _META_TTL_SECS (환경변수로 조정 가능)

    Args:
        hashed_user_id: compute_hashed_user_id()의 반환값 (PII 미포함)
        metadata      : IndexMetadata 인스턴스

    Raises:
        RuntimeError: Redis 연결 실패 시
    """
    await _ensure_redis_connected()

    key = _build_meta_key(hashed_user_id)
    payload = metadata.to_redis_dict()

    await redis_client.redis.hset(key, mapping=payload)
    await redis_client.redis.expire(key, _META_TTL_SECS)

    logger.info(
        "[PERSONALIZED_INDEX] Metadata saved to Redis (key_prefix=%s, ttl=%ds, vectors=%d)",
        _REDIS_META_PREFIX,
        _META_TTL_SECS,
        metadata.vector_count,
    )


async def load_index_metadata(hashed_user_id: str) -> Optional[IndexMetadata]:
    """
    Redis에서 FAISS 인덱스 메타데이터를 조회한다.

    Args:
        hashed_user_id: compute_hashed_user_id()의 반환값 (PII 미포함)

    Returns:
        IndexMetadata 인스턴스, 또는 키가 존재하지 않으면 None

    Raises:
        RuntimeError: Redis 연결 실패 시
    """
    await _ensure_redis_connected()

    key = _build_meta_key(hashed_user_id)
    raw = await redis_client.redis.hgetall(key)

    if not raw:
        logger.debug(
            "[PERSONALIZED_INDEX] No metadata found in Redis (key_prefix=%s).",
            _REDIS_META_PREFIX,
        )
        return None

    metadata = IndexMetadata.from_redis_dict(raw)
    logger.debug(
        "[PERSONALIZED_INDEX] Metadata loaded from Redis (vectors=%d)",
        metadata.vector_count,
    )
    return metadata


async def delete_index_metadata(hashed_user_id: str) -> None:
    """
    Redis에서 FAISS 인덱스 메타데이터를 영구 삭제한다.
    GDPR Right-to-Erasure 처리 파이프라인에서 호출된다.

    Args:
        hashed_user_id: compute_hashed_user_id()의 반환값 (PII 미포함)
    """
    await _ensure_redis_connected()

    key = _build_meta_key(hashed_user_id)
    deleted = await redis_client.redis.delete(key)

    if deleted:
        logger.info(
            "[PERSONALIZED_INDEX][GDPR] Metadata deleted from Redis (key_prefix=%s).",
            _REDIS_META_PREFIX,
        )
    else:
        logger.debug(
            "[PERSONALIZED_INDEX][GDPR] No metadata key to delete (key_prefix=%s).",
            _REDIS_META_PREFIX,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 고수준 오케스트레이션: 인덱스 초기화
# ─────────────────────────────────────────────────────────────────────────────


async def initialize_user_index(
    user_id: str,
    per_user_salt: str,
    cfg: PersonalizedRAGConfig,
) -> tuple[str, Path]:
    """
    사용자 식별자를 받아 결정론적 해시 경로를 생성하고 Redis 메타데이터를 초기화한다.
    인덱스 파일(.faiss) 자체는 이 함수에서 생성하지 않으며, 경로만 결정한다.

    처리 순서:
      1. KMS에서 global_pepper를 메모리로 페치
      2. SHA-256 해시 계산 → hashed_user_id 생성
      3. 결정론적 파일 경로 계산
      4. 인덱스 디렉토리 생성 (없는 경우)
      5. Redis에 초기 메타데이터 저장 (기존 데이터 없을 때만)

    Args:
        user_id       : 사용자 식별자 (PII — 내부에서 즉시 해시화 후 폐기)
        per_user_salt : DB에서 조회한 사용자별 솔트
        cfg           : PersonalizedRAGConfig 인스턴스 (bootstrap에서 주입)

    Returns:
        (hashed_user_id, index_path) 튜플

    Raises:
        FatalSecurityError : KMS 조회 치명 실패 시 (aws_client_wrapper 위임)
        PermissionError    : 디렉토리 생성 권한 부재 시
        ValueError         : 입력값 검증 실패 시
    """
    # 1. global_pepper: KMS → 메모리 (이 변수 외부로 절대 유출 금지)
    global_pepper = await fetch_global_pepper()

    # 2. PII를 해시화 → hashed_user_id (이후 user_id는 더 이상 사용하지 않는다)
    hashed_user_id = compute_hashed_user_id(user_id, per_user_salt, global_pepper)

    # 3. 파일 경로 계산
    index_path = build_index_path(hashed_user_id, cfg.storage_base_path)

    # 4. 디렉토리 보장
    ensure_index_directory(index_path)

    # 5. Redis 메타데이터: 이미 존재하면 skip (멱등성 보장)
    existing = await load_index_metadata(hashed_user_id)
    if existing is None:
        now = _now_utc_iso()
        initial_meta = IndexMetadata(
            created_at=now,
            updated_at=now,
            vector_count=0,
            index_path=str(index_path),
        )
        await save_index_metadata(hashed_user_id, initial_meta)
        logger.info(
            "[PERSONALIZED_INDEX] New user index initialized "
            "(masked_uid=%s, path_dir=%s).",
            mask_pii_id(user_id),
            index_path.parent,
        )
    else:
        logger.debug(
            "[PERSONALIZED_INDEX] User index already exists in Redis "
            "(masked_uid=%s, vectors=%d).",
            mask_pii_id(user_id),
            existing.vector_count,
        )

    return hashed_user_id, index_path


# ─────────────────────────────────────────────────────────────────────────────
# 비즈니스 로직: 수명 주기 및 컴팩션 정책
# ─────────────────────────────────────────────────────────────────────────────


def should_rebuild_index(metadata: IndexMetadata) -> bool:
    """
    인덱스 상태를 분석하여 재구축(Compaction)이 필요한지 여부를 판별한다.

    판단 기준:
      - 무의미한 Rebuild 방어: 삭제된 벡터(deleted_count)가 없으면 Rebuild는 단순 복사본 생성이 되므로 즉시 False 반환.
      - 기준 1. 물리적 규모 임계값 초과: '유효 벡터(vector_count)'가 아닌 '누적 벡터(total_count)'가 
                _COMPACTION_THRESHOLD를 초과하는지 검사. FAISS의 물리적 크기 팽창과 메모리 사용량은 total_count에 비례한다.
      - 기준 2. 삭제 비율 임계값 초과: (deleted_count / total_count)가 _DELETE_RATIO_THRESHOLD를 초과하는가?
                단, _MIN_DATASET_SIZE_FOR_COMPACTION 이하의 극소량 데이터셋에서는 일시적 변동 노이즈를 방지하기 위해 무시한다.

    Args:
        metadata: Redis에서 로드한 최신 인덱스 메타데이터

    Returns:
        True: 재구축 권장, False: 현재 상태 유지 가능
    """
    total_count = metadata.vector_count + metadata.deleted_count

    # 무의미한 Rebuild 방어: 치울 쓰레기가 없다면 컴팩션 트리거 불가
    if metadata.deleted_count == 0:
        return False

    # 기준 1: FAISS 물리적 규모가 너무 커진 경우 (조회/메모리 성능 최적화 필요)
    # [리뷰반영] 유효 벡터 수가 아닌 전체/누적 벡터 수(total_count)를 사용해 FAISS의 실제 압력을 가늠함.
    if total_count >= _COMPACTION_THRESHOLD:
        logger.info(
            "[PERSONALIZED_INDEX][POLICY] Compaction suggested: total_count (%d) >= threshold (%d)",
            total_count,
            _COMPACTION_THRESHOLD,
        )
        return True

    # 기준 2: 삭제된 데이터가 너무 많은 경우 (검색 품질 및 공간 효율성)
    if total_count >= _MIN_DATASET_SIZE_FOR_COMPACTION:
        delete_ratio = metadata.deleted_count / total_count
        if delete_ratio >= _DELETE_RATIO_THRESHOLD:
            logger.info(
                "[PERSONALIZED_INDEX][POLICY] Compaction suggested: delete_ratio (%.2f) >= threshold (%.2f)",
                delete_ratio,
                _DELETE_RATIO_THRESHOLD,
            )
            return True

    return False


class LuaScriptCache:
    """Lua 스크립트의 EVALSHA 캐시를 캡슐화하고, 연결 유실 시 자율 복구하는 헬퍼 클래스"""
    def __init__(self, script_body: str):
        self.script_body = script_body
        self._compiled: Optional["redis.commands.core.AsyncScript"] = None

    def get_or_register(self, client: "redis_async.Redis") -> "redis.commands.core.AsyncScript":
        # Coroutine 경쟁이 일어나더라도 register_script 의 부하가 미비하므로
        # 락 없이 단순화하여 인지 부담(Cognitive Load)을 줄임
        if self._compiled is None:
            self._compiled = client.register_script(self.script_body)
        return self._compiled

    def invalidate(self) -> None:
        self._compiled = None

# 모듈 레벨 캡슐화 객체 (단일 진실 공급원)
_meta_updater = LuaScriptCache(_LUA_UPDATE_META_SCRIPT)

async def _execute_update_meta_script(
    client: "redis_async.Redis",
    key: str,
    vector_delta: int,
    delete_delta: int,
    now: str,
    meta_updater: Optional[LuaScriptCache] = None,
) -> Optional[list[typing.Any]]:
    # 전역 인스턴스에 강제 종속되지 않도록 대체 캐시(DI) 허용
    updater = meta_updater or _meta_updater
    compiled_script = updater.get_or_register(client)

    # [리뷰반영] 예외 삼키기(Swallowing) 안티패턴을 제거하고 단일 헬퍼 사용
    # key가 문자열이 아닌 경우 명시적(Explicit) 에러가 발생하여 상위 버그를 조기 발견할 수 있음
    masked_uid = _extract_masked_uid_from_key(key)

    try:
        return await compiled_script(
            keys=[key],
            args=[str(vector_delta), str(delete_delta), str(now), str(_META_TTL_SECS)],
        )
    except (redis.exceptions.NoScriptError, redis.exceptions.ConnectionError) as e:
        # [리뷰반영] Transient 에러나 스크립트 리셋 상황(NOSCRIPT 등)에서만 캐시 무효화 수행
        updater.invalidate()
        logger.error(
            "[PERSONALIZED_INDEX] Failed to execute atomic Lua script for masked_uid=%s "
            "(Script Cache invalidated): %s",
            masked_uid,
            e,
        )
        raise
    except redis.exceptions.RedisError as e:
        # [리뷰반영] 일반적인 Redis 장애는 캐시 무효화 없이 로깅 후 상위 전파하여, "메타 부재(None)" 상황과 진짜 DB 장애를 명확히 구분
        logger.error(
            "[PERSONALIZED_INDEX] Redis error executing script for masked_uid=%s: %s",
            masked_uid,
            e,
        )
        raise


def _hgetall_list_to_dict(
    masked_uid: str,
    raw_list: typing.Any,
) -> Optional[dict[bytes | str, bytes | str]]:
    if not isinstance(raw_list, list) or len(raw_list) % 2 != 0:
        actual = len(raw_list) if isinstance(raw_list, list) else type(raw_list).__name__
        logger.error(
            "[PERSONALIZED_INDEX] Corrupted Redis metadata response for masked_uid=%s. "
            "Expected an even-length list from HGETALL, got length/type=%s.",
            masked_uid[:8],
            actual,
        )
        return None
    return dict(zip(raw_list[0::2], raw_list[1::2]))


async def update_index_after_op(
    hashed_user_id: str,
    vector_delta: int,
    delete_delta: int,
) -> Optional[IndexMetadata]:
    """
    [원자적(Atomic) 연산 기능 업데이트]
    벡터 추가/삭제 작업 후 메타데이터를 원자적으로 갱신하고, 컴팩션 필요 여부를 판단한다.

    Redis Lua Script를 사용하여 동시성(Race Condition) 환경에서도 'Read-Modify-Write' 시 
    데이터 갱신이 유실되지 않도록 보장한다. 갱신 후의 카운트는 항상 0 이상으로 유지된다.

    Args:
        hashed_user_id: 사용자 해시 ID
        vector_delta: 유효 벡터 수 변화량 (추가 시 +, 삭제 시 -)
        delete_delta: 무효(삭제 처리된) 벡터 수 변화량 (삭제 시 +)

    Returns:
        갱신된 IndexMetadata, 또는 대상 메타키가 존재하지 않으면 None
    """
    await _ensure_redis_connected()

    key = _build_meta_key(hashed_user_id)
    now = _now_utc_iso()

    # 분리된 Helper를 통해 스크립트 실행 (에러 시 raise되어 제어권 위임됨)
    raw_list = await _execute_update_meta_script(
        client=redis_client.redis,
        key=key,
        vector_delta=vector_delta,
        delete_delta=delete_delta,
        now=now,
    )
    
    if raw_list is None:
        logger.error(
            "[PERSONALIZED_INDEX] Cannot update metrics: No metadata found for masked_uid=%s",
            hashed_user_id[:8],
        )
        return None

    # 분리된 Helper를 통해 안전하게 파싱
    raw_dict = _hgetall_list_to_dict(hashed_user_id, raw_list)
    if raw_dict is None:
        return None

    metadata = IndexMetadata.from_redis_dict(raw_dict)

    if should_rebuild_index(metadata):
        logger.warning(
            "[PERSONALIZED_INDEX][ASYNC] Index for %s needs REBUILD. "
            "Please trigger background compaction worker.",
            hashed_user_id[:8],
        )

    return metadata

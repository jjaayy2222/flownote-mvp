# backend/core/config/streaming.py

"""
StreamingConfig — Phase 3 (Realtime Streaming) 설정 스키마 및 기본값 정의
=========================================================================

역할 (3-0 SSOT 정책에 따른 책임 분리):
  이 모듈은 스트리밍 관련 환경 변수의 '스키마 및 기본값 정의'만 담당합니다.
  실제 OS 환경 변수 로딩, 바운더리 체크(Clamping), 유효성 검증은
  3-5 정책에 따라 `backend/core/config_validator.py`에 위임됩니다.

하드코딩 금지:
  모든 수치 상수는 클래스 속성으로 중앙 정의합니다.
  개별 모듈에서 이 값들을 복사하거나 재정의하는 것을 금지합니다.

민감 정보 보호:
  이 모듈은 인증 토큰, 사용자 ID 등 민감 정보를 취급하지 않습니다.
  스트리밍 세션 식별은 hashed_user_id를 사용하며, 원문 ID는 로그에 기록하지 않습니다.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import ClassVar

from backend.config import ConfigRange, _clamp

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 환경 변수 키 상수 (문자열 하드코딩 방지 — 모듈 수준 정의)
# ─────────────────────────────────────────────────────────────────────────────

_ENV_KEEPALIVE_INTERVAL: str = "SSE_KEEPALIVE_INTERVAL_SECS"
_ENV_BUFFER_MAX_SIZE: str = "STREAM_BUFFER_MAX_SIZE"
_ENV_TIMEOUT: str = "STREAM_TIMEOUT_SECS"
_ENV_STREAM_VERSION: str = "LANGGRAPH_STREAM_VERSION"

# ─────────────────────────────────────────────────────────────────────────────
# 유효 범위 상수 (Clamping 규칙 중앙 정의 — 모듈 수준 정의)
# ─────────────────────────────────────────────────────────────────────────────

_KEEPALIVE_INTERVAL_RANGE: ConfigRange = ConfigRange(min=5, max=60)
_BUFFER_MAX_SIZE_RANGE: ConfigRange = ConfigRange(min=10, max=1000)
_TIMEOUT_RANGE: ConfigRange = ConfigRange(min=30, max=600)
_VALID_STREAM_VERSIONS: tuple[str, ...] = ("v1", "v2")

# ─────────────────────────────────────────────────────────────────────────────
# 기본값 상수 (Magic Numbers 제거 — 모듈 수준 정의)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_KEEPALIVE_INTERVAL_SECS: int = 15
_DEFAULT_BUFFER_MAX_SIZE: int = 100
_DEFAULT_TIMEOUT_SECS: int = 120
_DEFAULT_STREAM_VERSION: str = "v2"

# ─────────────────────────────────────────────────────────────────────────────
# 공개 상수 별칭 (외부 모듈 참조용 — 내부 구현과의 결합도 최소화)
# 외부 모듈은 _언더스코어 접두 상수가 아닌 이 공개 이름을 임포트해야 합니다.
# ─────────────────────────────────────────────────────────────────────────────

STREAMING_ENV_KEEPALIVE_INTERVAL: str = _ENV_KEEPALIVE_INTERVAL
STREAMING_ENV_BUFFER_MAX_SIZE: str = _ENV_BUFFER_MAX_SIZE
STREAMING_ENV_TIMEOUT: str = _ENV_TIMEOUT
STREAMING_ENV_STREAM_VERSION: str = _ENV_STREAM_VERSION

STREAMING_DEFAULT_KEEPALIVE_INTERVAL_SECS: int = _DEFAULT_KEEPALIVE_INTERVAL_SECS
STREAMING_DEFAULT_BUFFER_MAX_SIZE: int = _DEFAULT_BUFFER_MAX_SIZE
STREAMING_DEFAULT_TIMEOUT_SECS: int = _DEFAULT_TIMEOUT_SECS
STREAMING_DEFAULT_STREAM_VERSION: str = _DEFAULT_STREAM_VERSION

STREAMING_KEEPALIVE_INTERVAL_RANGE: ConfigRange = _KEEPALIVE_INTERVAL_RANGE
STREAMING_BUFFER_MAX_SIZE_RANGE: ConfigRange = _BUFFER_MAX_SIZE_RANGE
STREAMING_TIMEOUT_RANGE: ConfigRange = _TIMEOUT_RANGE
STREAMING_VALID_STREAM_VERSIONS: tuple[str, ...] = _VALID_STREAM_VERSIONS


# ─────────────────────────────────────────────────────────────────────────────
# 내부 파싱 헬퍼 (모듈 전용 — PII 비노출)
# ─────────────────────────────────────────────────────────────────────────────


def _load_int(key: str, default: int, range_: ConfigRange) -> int:
    """
    정수형 환경 변수를 로드하고 안전 범위로 Clamp한다.
    파싱 오류 시 기본값 폴백 + WARNING 로그.
    """
    raw = os.environ.get(key)
    if raw is None:
        return default

    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[STREAM][CONFIG] '%s' must be an integer, got type=%s. "
            "Falling back to default=%d.",
            key,
            type(raw).__name__,
            default,
        )
        return default

    clamped = _clamp(value, range_)
    if clamped != value:
        logger.warning(
            "[STREAM][CONFIG][CLAMP] '%s'=%d is outside safe range [%d, %d]; "
            "clamped to %d.",
            key,
            value,
            range_.min,
            range_.max,
            clamped,
        )
    return clamped


def _load_str_enum(key: str, default: str, valid_values: tuple[str, ...]) -> str:
    """
    문자열 열거형 환경 변수를 로드한다.
    환경 변수가 설정되지 않은 경우 default를 그대로 반환하여,
    기본값에 불필요한 .strip() 등의 조작이 가해지지 않도록 보장한다.
    유효하지 않은 값이면 기본값 폴백 + WARNING 로그.
    """
    # 두 단계 읽기: 먼저 존재 여부를 확인한 후 strip()을 적용
    # os.environ.get(key, default).strip() 패턴은 default에도 strip()을
    # 적용하여 의도치 않은 정규화를 유발할 수 있으므로 사용하지 않음
    if key not in os.environ:
        return default

    raw = os.environ[key].strip()
    if raw not in valid_values:
        logger.warning(
            "[STREAM][CONFIG] '%s'=%r is not a valid value. "
            "Allowed: %s. Falling back to default=%r.",
            key,
            raw,
            valid_values,
            default,
        )
        return default
    return raw


# ─────────────────────────────────────────────────────────────────────────────
# StreamingConfig 데이터 클래스 (명시적 타입 스키마)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class StreamingConfig:
    """
    실시간 스트리밍 파이프라인 런타임 설정값.

    역할: 환경 변수를 로드하여 타입이 지정된 설정 객체로 반환.
    유효성 검증(Fail-Fast) 및 Subsystem 등록은 `backend/core/config_validator.py`에서 수행.

    사용 예시:
        config = StreamingConfig.load()
        timeout = config.timeout_secs  # 정적 타입 추론 가능
    """

    # 런타임 설정값 (타입 명시 — IDE 자동완성 및 mypy 지원)
    keepalive_interval_secs: int = field(
        default_factory=lambda: _DEFAULT_KEEPALIVE_INTERVAL_SECS
    )
    buffer_max_size: int = field(default_factory=lambda: _DEFAULT_BUFFER_MAX_SIZE)
    timeout_secs: int = field(default_factory=lambda: _DEFAULT_TIMEOUT_SECS)
    stream_version: str = field(default_factory=lambda: _DEFAULT_STREAM_VERSION)

    # ── 스키마/범위 상수 노출 (외부 참조용 — ClassVar로 선언하여 인스턴스 필드에서 완전 제외) ────
    ENV_KEEPALIVE_INTERVAL: ClassVar[str] = _ENV_KEEPALIVE_INTERVAL
    ENV_BUFFER_MAX_SIZE: ClassVar[str] = _ENV_BUFFER_MAX_SIZE
    ENV_TIMEOUT: ClassVar[str] = _ENV_TIMEOUT
    ENV_STREAM_VERSION: ClassVar[str] = _ENV_STREAM_VERSION

    @classmethod
    def load(cls) -> "StreamingConfig":
        """
        환경 변수로부터 설정값을 로드하고 안전 범위로 보정(Clamp)하여 반환한다.
        파싱 오류 시 기본값으로 폴백 후 WARNING 로그를 남긴다.
        Subsystem 비활성화 결정은 config_validator.py에서 수행한다.
        """
        return cls(
            keepalive_interval_secs=_load_int(
                key=_ENV_KEEPALIVE_INTERVAL,
                default=_DEFAULT_KEEPALIVE_INTERVAL_SECS,
                range_=_KEEPALIVE_INTERVAL_RANGE,
            ),
            buffer_max_size=_load_int(
                key=_ENV_BUFFER_MAX_SIZE,
                default=_DEFAULT_BUFFER_MAX_SIZE,
                range_=_BUFFER_MAX_SIZE_RANGE,
            ),
            timeout_secs=_load_int(
                key=_ENV_TIMEOUT,
                default=_DEFAULT_TIMEOUT_SECS,
                range_=_TIMEOUT_RANGE,
            ),
            stream_version=_load_str_enum(
                key=_ENV_STREAM_VERSION,
                default=_DEFAULT_STREAM_VERSION,
                valid_values=_VALID_STREAM_VERSIONS,
            ),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 모듈 로드 시점 기본값 범위 점검 (Fail-fast 선행 조건 검사)
# assert 대신 명시적 예외를 사용하여 Python -O 모드에서도 검증 수행 보장
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_default_in_range(name: str, val: int, r: ConfigRange) -> None:
    """기본값이 정의된 안전 범위 내에 있는지 강제한다 (Production-safe)."""
    if not (r.min <= val <= r.max):
        raise RuntimeError(
            f"[STREAM][CONFIG][INVARIANT ERROR] Default {name}={val} is outside "
            f"allowed range [{r.min}, {r.max}]. Check streaming.py constants."
        )


def _ensure_default_in_list(name: str, val: str, allowed: tuple[str, ...]) -> None:
    """기본값이 허용된 목록에 있는지 강제한다 (Production-safe)."""
    if val not in allowed:
        raise RuntimeError(
            f"[STREAM][CONFIG][INVARIANT ERROR] Default {name}={val!r} is not in "
            f"allowed list {allowed}. Check streaming.py constants."
        )


# 기본값 정적 정합성 검사 실행
# (assert 대신 명시적 예외를 사용하여 Python -O 모드에서도 검증 수행 보장)
_ensure_default_in_range(
    "KEEPALIVE_INTERVAL", _DEFAULT_KEEPALIVE_INTERVAL_SECS, _KEEPALIVE_INTERVAL_RANGE
)
_ensure_default_in_range(
    "BUFFER_MAX_SIZE", _DEFAULT_BUFFER_MAX_SIZE, _BUFFER_MAX_SIZE_RANGE
)
_ensure_default_in_range("TIMEOUT", _DEFAULT_TIMEOUT_SECS, _TIMEOUT_RANGE)
_ensure_default_in_list(
    "STREAM_VERSION", _DEFAULT_STREAM_VERSION, _VALID_STREAM_VERSIONS
)

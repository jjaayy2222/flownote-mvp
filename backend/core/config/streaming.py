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

from backend.config import ConfigRange, _clamp

logger = logging.getLogger(__name__)


class StreamingConfig:
    """
    실시간 스트리밍 파이프라인 설정 스키마 및 기본값 정의.

    역할: 환경 변수 모델링 및 기본값 정의만 담당.
    유효성 검증 및 Subsystem 등록은 `backend/core/config_validator.py`에서 수행.
    """

    # ─────────────────────────────────────────────────────────────────────
    # 기본값 상수 (Magic Numbers 제거, 하드코딩 금지)
    # ─────────────────────────────────────────────────────────────────────

    DEFAULT_KEEPALIVE_INTERVAL_SECS: int = 15
    DEFAULT_BUFFER_MAX_SIZE: int = 100
    DEFAULT_TIMEOUT_SECS: int = 120
    DEFAULT_STREAM_VERSION: str = "v2"

    # ─────────────────────────────────────────────────────────────────────
    # 유효 범위 (Clamping 규칙 중앙 정의)
    # ─────────────────────────────────────────────────────────────────────

    KEEPALIVE_INTERVAL_RANGE: ConfigRange = ConfigRange(min=5, max=60)
    BUFFER_MAX_SIZE_RANGE: ConfigRange = ConfigRange(min=10, max=1000)
    TIMEOUT_RANGE: ConfigRange = ConfigRange(min=30, max=600)
    VALID_STREAM_VERSIONS: tuple[str, ...] = ("v1", "v2")

    # ─────────────────────────────────────────────────────────────────────
    # 환경 변수 키 상수 (문자열 하드코딩 방지)
    # ─────────────────────────────────────────────────────────────────────

    ENV_KEEPALIVE_INTERVAL = "SSE_KEEPALIVE_INTERVAL_SECS"
    ENV_BUFFER_MAX_SIZE = "STREAM_BUFFER_MAX_SIZE"
    ENV_TIMEOUT = "STREAM_TIMEOUT_SECS"
    ENV_STREAM_VERSION = "LANGGRAPH_STREAM_VERSION"

    # ─────────────────────────────────────────────────────────────────────
    # 런타임 로딩 (기본값 + Clamping 적용)
    # 실제 유효성 강제(Fail-Fast, Subsystem 등록)는 config_validator.py에 위임
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "StreamingConfig":
        """
        환경 변수로부터 설정값을 로드하고 안전 범위로 보정(Clamp)하여 반환한다.
        파싱 오류 시 기본값으로 폴백 후 WARNING 로그를 남긴다.
        Subsystem 비활성화 결정은 config_validator.py에서 수행한다.
        """
        instance = cls()

        # SSE keepalive 핑 간격
        instance.keepalive_interval_secs = cls._load_int(
            key=cls.ENV_KEEPALIVE_INTERVAL,
            default=cls.DEFAULT_KEEPALIVE_INTERVAL_SECS,
            range_=cls.KEEPALIVE_INTERVAL_RANGE,
        )

        # 토큰 큐 최대 크기
        instance.buffer_max_size = cls._load_int(
            key=cls.ENV_BUFFER_MAX_SIZE,
            default=cls.DEFAULT_BUFFER_MAX_SIZE,
            range_=cls.BUFFER_MAX_SIZE_RANGE,
        )

        # 스트리밍 세션 최대 허용 시간
        instance.timeout_secs = cls._load_int(
            key=cls.ENV_TIMEOUT,
            default=cls.DEFAULT_TIMEOUT_SECS,
            range_=cls.TIMEOUT_RANGE,
        )

        # LangGraph 스트리밍 API 버전
        instance.stream_version = cls._load_str_enum(
            key=cls.ENV_STREAM_VERSION,
            default=cls.DEFAULT_STREAM_VERSION,
            valid_values=cls.VALID_STREAM_VERSIONS,
        )

        return instance

    # ─────────────────────────────────────────────────────────────────────
    # 내부 파싱 헬퍼 (모듈 전용 — PII 비노출)
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def _load_int(cls, key: str, default: int, range_: ConfigRange) -> int:
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

    @classmethod
    def _load_str_enum(
        cls, key: str, default: str, valid_values: tuple[str, ...]
    ) -> str:
        """
        문자열 열거형 환경 변수를 로드한다.
        유효하지 않은 값이면 기본값 폴백 + WARNING 로그.
        """
        raw = os.environ.get(key, default).strip()
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

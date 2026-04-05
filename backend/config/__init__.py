# backend/config/__init__.py

"""
FlowNote MVP - 통합 설정 (클래스 기반)
"""

import sys
from pathlib import Path
import os
import logging
from dataclasses import dataclass
from typing import TypeVar, Union, Generic, Optional
from dotenv import load_dotenv

# 1️⃣ 프로젝트 루트 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# 2️⃣ 로컬 .env 로드 (우선!)
load_dotenv()

from openai import OpenAI

# 로거 설정
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────
# 유틸리티 함수 및 구조체
# ────────────────────────────────────────────────────────

T = TypeVar("T", int, float)


@dataclass(frozen=True, slots=True)
class ConfigRange(Generic[T]):
    """
    설정값의 범위를 정의하는 구조체 (Immutable)
    - slots=True를 통해 메모리 및 속도 최적화 (Python 3.10+)
    - 더 이상 NamedTuple이 아니므로 인덱싱이나 언패킹 대신 속성 접근(.min, .max)을 사용해야 합니다.
    """

    min: T
    max: T


def _clamp(value: T, r: ConfigRange[T]) -> T:
    """수치를 허용 범위(ConfigRange) 내로 제한하는 헬퍼 함수"""
    return max(r.min, min(value, r.max))


# 3️⃣ Streamlit 배포 환경에서 덮어쓰기
try:
    import streamlit as st

    if hasattr(st, "secrets"):
        for key in [
            "EMBEDDING_API_KEY",
            "EMBEDDING_BASE_URL",
            "EMBEDDING_MODEL",
            "EMBEDDING_LARGE_API_KEY",
            "EMBEDDING_LARGE_BASE_URL",
            "EMBEDDING_LARGE_MODEL",
            "GPT4O_API_KEY",
            "GPT4O_BASE_URL",
            "GPT4O_MODEL",
            "GPT4O_MINI_API_KEY",
            "GPT4O_MINI_BASE_URL",
            "GPT4O_MINI_MODEL",
            "GPT41_API_KEY",
            "GPT41_BASE_URL",
            "GPT41_MODEL",
        ]:
            if key in st.secrets and key not in os.environ:
                os.environ[key] = st.secrets[key]
except:
    pass

# 4️⃣ 이제부터 ModelConfig에서 os.getenv() 사용

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 모델 설정 클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


class ModelConfig:
    """OpenAI 모델 설정 관리 클래스"""

    # ===== GPT-4o =====
    GPT4O_API_KEY = os.getenv("GPT4O_API_KEY")
    GPT4O_BASE_URL = os.getenv("GPT4O_BASE_URL")
    GPT4O_MODEL = os.getenv("GPT4O_MODEL", "gpt-4o")

    # ===== GPT-4o-mini =====
    GPT4O_MINI_API_KEY = os.getenv("GPT4O_MINI_API_KEY")
    GPT4O_MINI_BASE_URL = os.getenv("GPT4O_MINI_BASE_URL")
    GPT4O_MINI_MODEL = os.getenv("GPT4O_MINI_MODEL", "gpt-4o-mini")

    # ===== 🆕 GPT-4.1 (Vision API) =====
    GPT41_API_KEY = os.getenv("GPT41_API_KEY")
    GPT41_BASE_URL = os.getenv("GPT41_BASE_URL")
    GPT41_MODEL = os.getenv("GPT41_MODEL", "gpt-4.1")

    # ===== Text-Embedding-3-Small =====
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")
    EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    # ===== Text-Embedding-3-Large =====
    EMBEDDING_LARGE_API_KEY = os.getenv("EMBEDDING_LARGE_API_KEY")
    EMBEDDING_LARGE_BASE_URL = os.getenv("EMBEDDING_LARGE_BASE_URL")
    EMBEDDING_LARGE_MODEL = os.getenv("EMBEDDING_LARGE_MODEL", "text-embedding-3-large")

    @classmethod
    def get_openai_client(cls, model_name: str) -> OpenAI:
        """
        OpenAI 클라이언트 생성 (범용)

        Args:
            model_name: 모델 이름 (예: "gpt-4o-mini", "gpt-4.1", "embedding")

        Returns:
            OpenAI: 설정된 클라이언트

        Raises:
            ValueError: 지원하지 않는 모델이거나 API 키가 없는 경우
        """
        # Embedding 모델 처리
        if "embedding" in model_name.lower():
            return cls.get_embedding_model(model_name)

        # 🆕 GPT-4.1 (Vision API)
        if "4.1" in model_name or "gpt-4.1" in model_name.lower():
            api_key = cls.GPT41_API_KEY
            base_url = cls.GPT41_BASE_URL
            model_display = "GPT-4.1"
        # GPT-4o-mini
        elif "4o-mini" in model_name or "mini" in model_name.lower():
            api_key = cls.GPT4O_MINI_API_KEY
            base_url = cls.GPT4O_MINI_BASE_URL
            model_display = "GPT-4o-mini"
        # GPT-4o
        elif "4o" in model_name:
            api_key = cls.GPT4O_API_KEY
            base_url = cls.GPT4O_BASE_URL
            model_display = "GPT-4o"
        else:
            raise ValueError(f"지원하지 않는 모델: {model_name}")

        # API 키 & Base URL 검증
        if not api_key:
            raise ValueError(f"{model_display} API 키가 설정되지 않았습니다!")
        if not base_url:
            raise ValueError(f"{model_display} BASE URL이 설정되지 않았습니다!")

        return OpenAI(base_url=base_url, api_key=api_key)

    @classmethod
    def get_embedding_model(cls, model_name: str) -> OpenAI:
        """
        Embedding 모델 클라이언트 생성

        Args:
            model_name: 임베딩 모델 이름

        Returns:
            OpenAI: 임베딩 클라이언트
        """
        if "large" in model_name.lower():
            api_key = cls.EMBEDDING_LARGE_API_KEY
            base_url = cls.EMBEDDING_LARGE_BASE_URL
            model_display = "Embedding Large"
        else:
            api_key = cls.EMBEDDING_API_KEY
            base_url = cls.EMBEDDING_BASE_URL
            model_display = "Embedding Small"

        if not api_key:
            raise ValueError(f"{model_display} API 키가 설정되지 않았습니다!")
        if not base_url:
            raise ValueError(f"{model_display} BASE URL이 설정되지 않았습니다!")

        return OpenAI(base_url=base_url, api_key=api_key)

    @classmethod
    def validate_config(cls):
        """모든 모델 설정 검증 및 출력"""
        print("\n🔍 Model Configuration Status:")
        print("=" * 50)

        # GPT-4o
        print(f"  GPT-4o:")
        print(f"    Model: {cls.GPT4O_MODEL}")
        print(
            f"    Status: {'✅ 설정됨' if cls.GPT4O_API_KEY and cls.GPT4O_BASE_URL else '❌ 없음'}"
        )

        # GPT-4o-mini
        print(f"\n  GPT-4o-mini:")
        print(f"    Model: {cls.GPT4O_MINI_MODEL}")
        print(
            f"    Status: {'✅ 설정됨' if cls.GPT4O_MINI_API_KEY and cls.GPT4O_MINI_BASE_URL else '❌ 없음'}"
        )

        # 🆕 GPT-4.1
        print(f"\n  🆕 GPT-4.1 (Vision API):")
        print(f"    Model: {cls.GPT41_MODEL}")
        print(f"    Base URL: {cls.GPT41_BASE_URL}")
        print(
            f"    Status: {'✅ 설정됨' if cls.GPT41_API_KEY and cls.GPT41_BASE_URL else '❌ 없음'}"
        )

        # Embedding Small
        print(f"\n  Embedding Small:")
        print(f"    Model: {cls.EMBEDDING_MODEL}")
        print(
            f"    Status: {'✅ 설정됨' if cls.EMBEDDING_API_KEY and cls.EMBEDDING_BASE_URL else '❌ 없음'}"
        )

        # Embedding Large
        print(f"\n  Embedding Large:")
        print(f"    Model: {cls.EMBEDDING_LARGE_MODEL}")
        print(
            f"    Status: {'✅ 설정됨' if cls.EMBEDDING_LARGE_API_KEY and cls.EMBEDDING_LARGE_BASE_URL else '❌ 없음'}"
        )

        print("=" * 50)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# Redis 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


class RedisConfig:
    """Redis 설정"""

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 알림(Alerting) 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


class AlertConfig:
    """Discord 및 시스템 알림 설정"""

    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
    
    # 동일 에러 재발송 방지 시간 (초)
    DEFAULT_THROTTLE_SECONDS = 300 # 5분
    
    # 심각도별 색상 (Discord Embed용)
    COLOR_CRITICAL = 0xFF0000 # Red
    COLOR_WARNING = 0xFFAA00  # Orange
    COLOR_INFO = 0x00AAFF     # Blue



# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# WebSocket 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


class WebSocketConfig:
    """WebSocket 설정"""

    # 1️⃣ 기본값 및 임계값 정의 (Magic Numbers 제거)
    DEFAULT_COMPRESSION_THRESHOLD = 1024
    DEFAULT_METRICS_MAX_TPS = 100
    DEFAULT_METRICS_WINDOW_SECONDS = 60

    TPS_RANGE = ConfigRange(min=1, max=1000)
    WINDOW_RANGE = ConfigRange(min=1, max=3600)

    # 2️⃣ 설정 파싱 및 검증
    # 압축 적용 임계값 (기본: 1KB)
    _RAW_COMP_THRESH = os.getenv(
        "WS_COMPRESSION_THRESHOLD", str(DEFAULT_COMPRESSION_THRESHOLD)
    )
    try:
        COMPRESSION_THRESHOLD = int(_RAW_COMP_THRESH)
    except (ValueError, TypeError):
        COMPRESSION_THRESHOLD = DEFAULT_COMPRESSION_THRESHOLD
        logger.warning(
            "Invalid WS_COMPRESSION_THRESHOLD=%r; falling back to default %s",
            _RAW_COMP_THRESH,
            DEFAULT_COMPRESSION_THRESHOLD,
        )

    # Metrics 관련 설정
    # TPS 계산용 최대 샘플 수
    _RAW_MAX_TPS_ENV = os.getenv("WS_METRICS_MAX_TPS", str(DEFAULT_METRICS_MAX_TPS))
    try:
        _RAW_MAX_TPS = int(_RAW_MAX_TPS_ENV)
    except (ValueError, TypeError):
        _RAW_MAX_TPS = DEFAULT_METRICS_MAX_TPS
        logger.warning(
            "Invalid WS_METRICS_MAX_TPS=%r; falling back to default %s",
            _RAW_MAX_TPS_ENV,
            DEFAULT_METRICS_MAX_TPS,
        )
    METRICS_MAX_TPS = _clamp(_RAW_MAX_TPS, TPS_RANGE)

    # TPS 계산 시간 윈도우
    _RAW_WINDOW_ENV = os.getenv(
        "WS_METRICS_WINDOW_SECONDS", str(DEFAULT_METRICS_WINDOW_SECONDS)
    )
    try:
        _RAW_WINDOW = int(_RAW_WINDOW_ENV)
    except (ValueError, TypeError):
        _RAW_WINDOW = DEFAULT_METRICS_WINDOW_SECONDS
        logger.warning(
            "Invalid WS_METRICS_WINDOW_SECONDS=%r; falling back to default %s seconds",
            _RAW_WINDOW_ENV,
            DEFAULT_METRICS_WINDOW_SECONDS,
        )
    METRICS_WINDOW_SECONDS = _clamp(_RAW_WINDOW, WINDOW_RANGE)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 경로 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


class PathConfig:
    """프로젝트 경로 설정"""

    BASE_DIR = Path(__file__).parent.parent.parent  # 프로젝트 루트
    DATA_DIR = BASE_DIR / "data"
    UPLOAD_DIR = DATA_DIR / "uploads"
    DB_DIR = DATA_DIR / "db"
    FAISS_INDEX_DIR = DATA_DIR / "faiss"

    # 필수 디렉토리 생성
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)
    FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 앱 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━



class AppConfig:
    """애플리케이션 설정"""

    # Streamlit 설정
    PAGE_TITLE = "FlowNote MVP"
    PAGE_ICON = "📚"
    LAYOUT = "wide"

    # 파일 업로드 설정
    MAX_FILE_SIZE = 200  # MB
    ALLOWED_EXTENSIONS = ["pdf", "txt", "md", "docx"]

    # 검색 설정
    DEFAULT_TOP_K = 5
    SIMILARITY_THRESHOLD = 0.7

    # 자동화 설정
    ARCHIVE_DAYS_THRESHOLD = 30  # 아카이브 기준일 (미접근 기간)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 어드민 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


class AdminConfig:
    """관리자 권한 및 인증 설정"""

    @staticmethod
    def get_admin_key() -> Optional[str]:
        """
        ADMIN_API_KEY를 환경 변수에서 조회한다.
        모듈 로드 시점이 아닌 호출 시점에 조회하여 핫 리로드 및 테스트 유연성 확보.
        """
        return os.getenv("ADMIN_API_KEY")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔧 래퍼 함수 & 상수 (직접 임포트용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


def get_embedding_model(model_name: str):
    """래퍼 함수 - 직접 임포트 가능"""
    return ModelConfig.get_embedding_model(model_name)


# 📌 app.py에서 사용할 상수들
EMBEDDING_MODEL = ModelConfig.EMBEDDING_MODEL
EMBEDDING_COSTS = {
    "text-embedding-3-small": 0.02 / 1_000_000,
    "text-embedding-3-large": 0.13 / 1_000_000,
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 실행 (테스트용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    # 설정 검증
    ModelConfig.validate_config()

    # 경로 확인
    print("\n📁 Path Configuration:")
    print(f"  BASE_DIR: {PathConfig.BASE_DIR}")
    print(f"  DATA_DIR: {PathConfig.DATA_DIR}")
    print(f"  UPLOAD_DIR: {PathConfig.UPLOAD_DIR}")
    print(f"  DB_DIR: {PathConfig.DB_DIR}")


"""result_4 - ❌ Missing configuration in .env file

    🔍 Model Configuration Status:
    ==================================================
    GPT-4o:
        Model: openai/gpt-4o
        Status: ✅ 설정됨

    GPT-4o-mini:
        Model: openai/gpt-4o-mini
        Status: ✅ 설정됨

    🆕 GPT-4.1 (Vision API):
        Model: gpt-4.1
        Base URL: None
        Status: ❌ 없음

    Embedding Small:
        Model: text-embedding-3-small
        Status: ✅ 설정됨

    Embedding Large:
        Model: openai/text-embedding-3-large
        Status: ✅ 설정됨
    ==================================================

    📁 Path Configuration:
    BASE_DIR: /Users/jay/ICT-projects/flownote-mvp
    DATA_DIR: /Users/jay/ICT-projects/flownote-mvp/data
    UPLOAD_DIR: /Users/jay/ICT-projects/flownote-mvp/data/uploads
    DB_DIR: /Users/jay/ICT-projects/flownote-mvp/data/db

"""

"""result_5 - ⭕️ Configured successfully

    - .env에서 환경변수 이름 수정 후 성공 

    🔍 Model Configuration Status:
    ==================================================
    GPT-4o:
        Model: openai/gpt-4o
        Status: ✅ 설정됨

    GPT-4o-mini:
        Model: openai/gpt-4o-mini
        Status: ✅ 설정됨

    🆕 GPT-4.1 (Vision API):
        Model: openai/gpt-4.1
        Base URL: https://ml********
        Status: ✅ 설정됨

    Embedding Small:
        Model: text-embedding-3-small
        Status: ✅ 설정됨

    Embedding Large:
        Model: openai/text-embedding-3-large
        Status: ✅ 설정됨
    ==================================================

    📁 Path Configuration:
    BASE_DIR: /Users/jay/ICT-projects/flownote-mvp
    DATA_DIR: /Users/jay/ICT-projects/flownote-mvp/data
    UPLOAD_DIR: /Users/jay/ICT-projects/flownote-mvp/data/uploads
    DB_DIR: /Users/jay/ICT-projects/flownote-mvp/data/db

"""


"""test_result_6 - ⭕️ Configured successfully

    - Class method + 함수형 method 분리 테스트

    🔍 Model Configuration Status:
    ==================================================
    GPT-4o:
        Model: openai/gpt-4o
        Status: ✅ 설정됨

    GPT-4o-mini:
        Model: openai/gpt-4o-mini
        Status: ✅ 설정됨

    🆕 GPT-4.1 (Vision API):
        Model: openai/gpt-4.1
        Base URL: https://ml********
        Status: ✅ 설정됨

    Embedding Small:
        Model: text-embedding-3-small
        Status: ✅ 설정됨

    Embedding Large:
        Model: openai/text-embedding-3-large
        Status: ✅ 설정됨
    ==================================================

    📁 Path Configuration:
    BASE_DIR: /Users/jay/ICT-projects/flownote-mvp
    DATA_DIR: /Users/jay/ICT-projects/flownote-mvp/data
    UPLOAD_DIR: /Users/jay/ICT-projects/flownote-mvp/data/uploads
    DB_DIR: /Users/jay/ICT-projects/flownote-mvp/data/db

"""

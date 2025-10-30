# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/config.py (클래스 기반 리팩토리 + gpt 4.1 추가)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 통합 설정 (클래스 기반)
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# 환경 변수 로드
load_dotenv()


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
        print(f"    Status: {'✅ 설정됨' if cls.GPT4O_API_KEY and cls.GPT4O_BASE_URL else '❌ 없음'}")
        
        # GPT-4o-mini
        print(f"\n  GPT-4o-mini:")
        print(f"    Model: {cls.GPT4O_MINI_MODEL}")
        print(f"    Status: {'✅ 설정됨' if cls.GPT4O_MINI_API_KEY and cls.GPT4O_MINI_BASE_URL else '❌ 없음'}")
        
        # 🆕 GPT-4.1
        print(f"\n  🆕 GPT-4.1 (Vision API):")
        print(f"    Model: {cls.GPT41_MODEL}")
        print(f"    Base URL: {cls.GPT41_BASE_URL}")
        print(f"    Status: {'✅ 설정됨' if cls.GPT41_API_KEY and cls.GPT41_BASE_URL else '❌ 없음'}")
        
        # Embedding Small
        print(f"\n  Embedding Small:")
        print(f"    Model: {cls.EMBEDDING_MODEL}")
        print(f"    Status: {'✅ 설정됨' if cls.EMBEDDING_API_KEY and cls.EMBEDDING_BASE_URL else '❌ 없음'}")
        
        # Embedding Large
        print(f"\n  Embedding Large:")
        print(f"    Model: {cls.EMBEDDING_LARGE_MODEL}")
        print(f"    Status: {'✅ 설정됨' if cls.EMBEDDING_LARGE_API_KEY and cls.EMBEDDING_LARGE_BASE_URL else '❌ 없음'}")
        
        print("=" * 50)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 경로 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

class PathConfig:
    """프로젝트 경로 설정"""
    
    BASE_DIR = Path(__file__).parent.parent  # 프로젝트 루트
    DATA_DIR = BASE_DIR / "data"
    UPLOAD_DIR = DATA_DIR / "uploads"
    DB_DIR = DATA_DIR / "db"
    
    # 필수 디렉토리 생성
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)


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
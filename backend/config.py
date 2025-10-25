# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/config.py (확장)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 통합 설정 관리
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 프로젝트 루트 경로
ROOT_DIR = Path(__file__).parent.parent

# 데이터 경로
DATA_DIR = ROOT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
FAISS_DIR = DATA_DIR / "faiss"
EXPORTS_DIR = DATA_DIR / "exports"

# 폴더 생성
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
FAISS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# OpenAI 관련 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

class OpenAIConfig:
    """OpenAI 모델 설정"""
    
    # GPT-4o (Chat - 고성능)
    GPT4O_API_KEY = os.getenv("GPT4O_API_KEY")
    GPT4O_BASE_URL = os.getenv("GPT4O_BASE_URL")
    GPT4O_MODEL = os.getenv("GPT4O_MODEL", "openai/gpt-4o")
    
    # GPT-4o-mini (Chat - 빠르고 저렴) ⭐️ 주로 사용!
    GPT4O_MINI_API_KEY = os.getenv("GPT4O_MINI_API_KEY")
    GPT4O_MINI_BASE_URL = os.getenv("GPT4O_MINI_BASE_URL")
    GPT4O_MINI_MODEL = os.getenv("GPT4O_MINI_MODEL", "openai/gpt-4o-mini")
    
    # Text-Embedding-3-Small (벡터 검색용) ⭐️ FAISS 사용!
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")
    EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    
    # Text-Embedding-3-Large (고성능 임베딩)
    EMBEDDING_LARGE_API_KEY = os.getenv("EMBEDDING_LARGE_API_KEY")
    EMBEDDING_LARGE_BASE_URL = os.getenv("EMBEDDING_LARGE_BASE_URL")
    EMBEDDING_LARGE_MODEL = os.getenv("EMBEDDING_LARGE_MODEL", "openai/text-embedding-3-large")
    
    # 임베딩 차원
    EMBEDDING_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Anthropic 관련 설정 (OpenAI 호환!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ClaudeConfig:
    """Claude 모델 설정 (OpenAI 호환 API)"""
    
    # Claude-4-Sonnet (강력한 추론)
    CLAUDE_4_SONNET_API_KEY = os.getenv("CLAUDE_4_SONNET_API_KEY")
    CLAUDE_4_SONNET_BASE_URL = os.getenv("CLAUDE_4_SONNET_BASE_URL")
    CLAUDE_4_SONNET_MODEL = os.getenv("CLAUDE_4_SONNET_MODEL", "anthropic/claude-sonnet-4")
    
    # Claude-3.5-Haiku (빠른 응답)
    CLAUDE_3_5_HAIKU_API_KEY = os.getenv("CLAUDE_3.5_HAIKU_API_KEY")
    CLAUDE_3_5_HAIKU_BASE_URL = os.getenv("CLAUDE_3.5_HAIKU_BASE_URL")
    CLAUDE_3_5_HAIKU_MODEL = os.getenv("CLAUDE_3.5_HAIKU_MODEL", "anthropic/claude-3-5-haiku")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 청킹 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

class ChunkingConfig:
    """텍스트 청킹 설정"""
    
    CHUNK_SIZE = 500                        # 청크 크기 (글자 수)
    CHUNK_OVERLAP = 100                     # 청크 겹침 (글자 수)
    MIN_CHUNK_SIZE = 50                     # 최소 청크 크기


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 비용 계산 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

class CostConfig:
    """API 비용 계산 설정"""
    
    # OpenAI 임베딩 비용 (per 1M tokens)
    EMBEDDING_COST = {
        "text-embedding-3-small": 0.02,     # $0.02 / 1M tokens
        "text-embedding-3-large": 0.13      # $0.13 / 1M tokens
    }
    
    # Chat 모델 비용 (per 1M tokens)
    CHAT_COST = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "claude-sonnet-4": {"input": 3.00, "output": 15.00},
        "claude-3-5-haiku": {"input": 1.00, "output": 5.00}
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 설정 클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

class Config:
    """FlowNote MVP 통합 설정"""
    
    # 하위 설정 클래스
    openai = OpenAIConfig
    claude = ClaudeConfig
    chunking = ChunkingConfig
    cost = CostConfig
    
    # 프로젝트 정보
    PROJECT_NAME = "FlowNote MVP"
    VERSION = "0.1.0"
    
    # 기본 모델 선택
    DEFAULT_CHAT_MODEL = "gpt-4o-mini"
    DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
    
    @classmethod
    def get_embedding_client(cls, model="small"):
        """임베딩 클라이언트 생성"""
        from openai import OpenAI
        
        if model == "small":
            return OpenAI(
                api_key=cls.openai.EMBEDDING_API_KEY,
                base_url=cls.openai.EMBEDDING_BASE_URL
            )
        elif model == "large":
            return OpenAI(
                api_key=cls.openai.EMBEDDING_LARGE_API_KEY,
                base_url=cls.openai.EMBEDDING_LARGE_BASE_URL
            )
        else:
            raise ValueError(f"Unknown embedding model: {model}")
    
    @classmethod
    def get_chat_client(cls, model="gpt-4o-mini"):
        """챗 클라이언트 생성"""
        from openai import OpenAI
        
        if model == "gpt-4o":
            return OpenAI(
                api_key=cls.openai.GPT4O_API_KEY,
                base_url=cls.openai.GPT4O_BASE_URL
            )
        elif model == "gpt-4o-mini":
            return OpenAI(
                api_key=cls.openai.GPT4O_MINI_API_KEY,
                base_url=cls.openai.GPT4O_MINI_BASE_URL
            )
        elif model == "claude-sonnet-4":
            return OpenAI(
                api_key=cls.claude.CLAUDE_4_SONNET_API_KEY,
                base_url=cls.claude.CLAUDE_4_SONNET_BASE_URL
            )
        elif model == "claude-3-5-haiku":
            return OpenAI(
                api_key=cls.claude.CLAUDE_3_5_HAIKU_API_KEY,
                base_url=cls.claude.CLAUDE_3_5_HAIKU_BASE_URL
            )
        else:
            raise ValueError(f"Unknown chat model: {model}")

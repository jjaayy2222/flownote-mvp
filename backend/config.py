# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/config.py 
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote 설정 파일
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

# ===================================
# OpenAI API 설정 (3개 모델)
# ===================================

# GPT-4o (Chat - 고성능)
GPT4O_API_KEY = os.getenv("GPT4O_API_KEY")
GPT4O_BASE_URL = os.getenv("GPT4O_BASE_URL")
GPT4O_MODEL = os.getenv("GPT4O_MODEL", "openai/gpt-4o")

# GPT-4o-mini (Chat - 빠르고 저렴) ⭐️ 주력 모델
GPT4O_MINI_API_KEY = os.getenv("GPT4O_MINI_API_KEY")
GPT4O_MINI_BASE_URL = os.getenv("GPT4O_MINI_BASE_URL")
GPT4O_MINI_MODEL = os.getenv("GPT4O_MINI_MODEL", "openai/gpt-4o-mini")

# Text-Embedding-3-Small (벡터 검색) ⭐️ FAISS용
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# ===================================
# 청킹 설정
# ===================================
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

# ===================================
# 함수: API 클라이언트 생성
# ===================================

def get_chat_client(model="mini"):
    """
    Chat 클라이언트 반환
    
    Args:
        model: "mini" (기본) 또는 "full"
    
    Returns:
        OpenAI client
    """
    from openai import OpenAI
    
    if model == "mini":
        return OpenAI(
            base_url=GPT4O_MINI_BASE_URL,
            api_key=GPT4O_MINI_API_KEY
        )
    else:  # "full"
        return OpenAI(
            base_url=GPT4O_BASE_URL,
            api_key=GPT4O_API_KEY
        )

def get_embedding_client():
    """
    Embedding 클라이언트 반환
    
    Returns:
        OpenAI client
    """
    from openai import OpenAI
    
    return OpenAI(
        base_url=EMBEDDING_BASE_URL,
        api_key=EMBEDDING_API_KEY
    )

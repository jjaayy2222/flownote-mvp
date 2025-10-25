# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/config.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


"""
FlowNote MVP - 통합 설정
"""

"""
FlowNote MVP - 통합 설정
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# 환경 변수 로드
load_dotenv()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# API 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

# GPT-4o
GPT4O_API_KEY = os.getenv("GPT4O_API_KEY")
GPT4O_BASE_URL = os.getenv("GPT4O_BASE_URL")
GPT4O_MODEL = os.getenv("GPT4O_MODEL")

# GPT-4o-mini
GPT4O_MINI_API_KEY = os.getenv("GPT4O_MINI_API_KEY")
GPT4O_MINI_BASE_URL = os.getenv("GPT4O_MINI_BASE_URL")
GPT4O_MINI_MODEL = os.getenv("GPT4O_MINI_MODEL")

# Text-Embedding-3-Small
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Text-Embedding-3-Large
EMBEDDING_LARGE_API_KEY = os.getenv("EMBEDDING_LARGE_API_KEY")
EMBEDDING_LARGE_BASE_URL = os.getenv("EMBEDDING_LARGE_BASE_URL")
EMBEDDING_LARGE_MODEL = os.getenv("EMBEDDING_LARGE_MODEL", "openai/text-embedding-3-large")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 임베딩 비용 (1M 토큰당 USD)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

EMBEDDING_COSTS = {
    "text-embedding-3-small": 0.02 / 1_000_000,
    "text-embedding-3-large": 0.13 / 1_000_000,
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 클라이언트 생성 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_embedding_model(model_name: str = None):
    """임베딩 모델 클라이언트 생성"""
    if model_name is None:
        model_name = EMBEDDING_MODEL
    
    if "large" in model_name.lower():
        api_key = EMBEDDING_LARGE_API_KEY
        base_url = EMBEDDING_LARGE_BASE_URL
    else:
        api_key = EMBEDDING_API_KEY
        base_url = EMBEDDING_BASE_URL
    
    if not api_key:
        raise ValueError(f"{model_name} API 키가 설정되지 않았습니다!")
    
    if not base_url:
        raise ValueError(f"{model_name} BASE URL이 설정되지 않았습니다!")
    
    return OpenAI(base_url=base_url, api_key=api_key)


def get_openai_client(model_name: str):
    """OpenAI 클라이언트 생성 (범용)"""
    if "embedding" in model_name.lower():
        return get_embedding_model(model_name)
    
    if "4o-mini" in model_name:
        api_key = GPT4O_MINI_API_KEY
        base_url = GPT4O_MINI_BASE_URL
    elif "4o" in model_name:
        api_key = GPT4O_API_KEY
        base_url = GPT4O_BASE_URL
    else:
        raise ValueError(f"지원하지 않는 모델: {model_name}")
    
    if not api_key:
        raise ValueError(f"{model_name} API 키가 설정되지 않았습니다!")
    
    if not base_url:
        raise ValueError(f"{model_name} BASE URL이 설정되지 않았습니다!")
    
    return OpenAI(base_url=base_url, api_key=api_key)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 프로젝트 경로
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
FAISS_DIR = DATA_DIR / "faiss"
EXPORTS_DIR = DATA_DIR / "exports"

# 디렉토리 생성
for dir_path in [DATA_DIR, UPLOADS_DIR, FAISS_DIR, EXPORTS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    print("=" * 50)
    print("설정 확인")
    print("=" * 50)
    
    print(f"\n📁 프로젝트 경로:")
    print(f"   - ROOT: {PROJECT_ROOT}")
    print(f"   - DATA: {DATA_DIR}")
    
    print(f"\n🔑 API 키 확인:")
    print(f"   - GPT4O: {'✅ 설정됨' if GPT4O_API_KEY else '❌ 없음'}")
    print(f"   - GPT4O_MINI: {'✅ 설정됨' if GPT4O_MINI_API_KEY else '❌ 없음'}")
    print(f"   - EMBEDDING: {'✅ 설정됨' if EMBEDDING_API_KEY else '❌ 없음'}")
    print(f"   - EMBEDDING_LARGE: {'✅ 설정됨' if EMBEDDING_LARGE_API_KEY else '❌ 없음'}")
    
    print(f"\n🤖 모델:")
    print(f"   - GPT4O: {GPT4O_MODEL}")
    print(f"   - GPT4O_MINI: {GPT4O_MINI_MODEL}")
    print(f"   - EMBEDDING: {EMBEDDING_MODEL}")
    print(f"   - EMBEDDING_LARGE: {EMBEDDING_LARGE_MODEL}")
    
    try:
        client = get_embedding_model()
        print("\n✅ 임베딩 클라이언트 생성 성공!")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
    
    print("\n" + "=" * 50)



"""result_2

    ==================================================
    설정 확인
    ==================================================

    📁 프로젝트 경로:
        - ROOT: /Users/jay/ICT-projects/flownote-mvp
        - DATA: /Users/jay/ICT-projects/flownote-mvp/data

    🔑 API 키 확인:
        - GPT4O: ✅ 설정됨
        - GPT4O_MINI: ✅ 설정됨
        - EMBEDDING: ✅ 설정됨
        - EMBEDDING_LARGE: ✅ 설정됨

    🌐 BASE URL 확인:
        - GPT4O: https://mlapi.run/0e6857e3-a90b-4c99-93ac-1f9f887a...
        - GPT4O_MINI: https://mlapi.run/40cc17ae-a89b-4f12-a7d6-13293180...
        - EMBEDDING: https://mlapi.run/b54ff33e-6d14-42df-93f9-0f113216...
        - EMBEDDING_LARGE: https://mlapi.run/4aae6995-00ec-445b-bfc1-cc2689af...

    🤖 모델:
        - GPT4O: openai/gpt-4o
        - GPT4O_MINI: openai/gpt-4o-mini
        - EMBEDDING: text-embedding-3-small
        - EMBEDDING_LARGE: openai/text-embedding-3-large

    💰 비용 (1M 토큰당):
        - text-embedding-3-small: $0.02
        - text-embedding-3-large: $0.13

    ==================================================
    클라이언트 생성 테스트
    ==================================================

    ✅ 임베딩 클라이언트 생성 성공!
        - 모델: text-embedding-3-small
        - URL: https://mlapi.run/b54ff33e-6d14-42df-93f9-0f1132160ee8/v1

    ==================================================

"""



"""result_3

    ==================================================
    설정 확인
    ==================================================

    📁 프로젝트 경로:
        - ROOT: /Users/jay/ICT-projects/flownote-mvp
        - DATA: /Users/jay/ICT-projects/flownote-mvp/data

    🔑 API 키 확인:
        - GPT4O: ✅ 설정됨
        - GPT4O_MINI: ✅ 설정됨
        - EMBEDDING: ✅ 설정됨
        - EMBEDDING_LARGE: ✅ 설정됨

    🤖 모델:
        - GPT4O: openai/gpt-4o
        - GPT4O_MINI: openai/gpt-4o-mini
        - EMBEDDING: text-embedding-3-small
        - EMBEDDING_LARGE: openai/text-embedding-3-large

    ✅ 임베딩 클라이언트 생성 성공!

==================================================

"""
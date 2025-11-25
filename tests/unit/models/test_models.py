# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# tests/test_new_models.py (수정!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
새로 발급받은 API 테스트
- text-embedding-3-large
- claude-4-sonnet
- claude-3.5-haiku

Anthropic 라이브러리
- base_url 미지원
- OpenAI 호환 엔드포인트 필요
- OpenAI 라이브러리 사용 →  OpenAI 호환 모드로 사용해야 함
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

# 환경 변수 로드
load_dotenv()

print("=" * 50)
print("새 API 모델 테스트")
print("=" * 50)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Text-Embedding-3-Large 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n1. Text-Embedding-3-Large 테스트")
print("-" * 50)

try:
    client = OpenAI(
        api_key=os.getenv("EMBEDDING_LARGE_API_KEY"),
        base_url=os.getenv("EMBEDDING_LARGE_BASE_URL")
    )
    
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input="FlowNote는 AI 기반 문서 관리 도구입니다."
    )
    
    embedding = response.data[0].embedding
    dimensions = len(embedding)
    
    print(f"✅ 임베딩 성공!")
    print(f"   - 모델: text-embedding-3-large")
    print(f"   - 벡터 차원: {dimensions}")
    print(f"   - 토큰 사용: {response.usage.total_tokens}")
    
except Exception as e:
    print(f"❌ 에러: {str(e)}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Claude-4-Sonnet 테스트 (OpenAI 호환!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n2. Claude-4-Sonnet 테스트")
print("-" * 50)

try:
    # OpenAI 라이브러리 사용!
    client = OpenAI(
        api_key=os.getenv("CLAUDE_4_SONNET_API_KEY"),
        base_url=os.getenv("CLAUDE_4_SONNET_BASE_URL")
    )
    
    # OpenAI 호환 형식!
    response = client.chat.completions.create(
        model=os.getenv("CLAUDE_4_SONNET_MODEL"),
        messages=[
            {
                "role": "user",
                "content": "FlowNote에 대해 한 문장으로 설명해주세요."
            }
        ],
        max_tokens=100
    )
    
    response_text = response.choices[0].message.content
    
    print(f"✅ 응답 성공!")
    print(f"   - 모델: {os.getenv('CLAUDE_4_SONNET_MODEL')}")
    print(f"   - 응답: {response_text}")
    print(f"   - 토큰 사용: {response.usage.total_tokens}")
    
except Exception as e:
    print(f"❌ 에러: {str(e)}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Claude-3.5-Haiku 테스트 (OpenAI 호환!)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n3. Claude-3.5-Haiku 테스트")
print("-" * 50)

try:
    # OpenAI 라이브러리 사용!
    client = OpenAI(
        api_key=os.getenv("CLAUDE_3.5_HAIKU_API_KEY"),
        base_url=os.getenv("CLAUDE_3.5_HAIKU_BASE_URL")
    )
    
    # OpenAI 호환 형식!
    response = client.chat.completions.create(
        model=os.getenv("CLAUDE_3.5_HAIKU_MODEL"),
        messages=[
            {
                "role": "user",
                "content": "안녕하세요! 빠른 응답 테스트입니다."
            }
        ],
        max_tokens=100
    )
    
    response_text = response.choices[0].message.content
    
    print(f"✅ 응답 성공!")
    print(f"   - 모델: {os.getenv('CLAUDE_3.5_HAIKU_MODEL')}")
    print(f"   - 응답: {response_text}")
    print(f"   - 토큰 사용: {response.usage.total_tokens}")
    
except Exception as e:
    print(f"❌ 에러: {str(e)}")

print("\n" + "=" * 50)
print("테스트 완료!")
print("=" * 50)


"""result

    ==================================================
    새 API 모델 테스트
    ==================================================

    1. Text-Embedding-3-Large 테스트
    --------------------------------------------------
    ✅ 임베딩 성공!
        - 모델: text-embedding-3-large
        - 벡터 차원: 3072
        - 토큰 사용: 16

    2. Claude-4-Sonnet 테스트
    --------------------------------------------------
    ✅ 응답 성공!
        - 모델: anthropic/claude-sonnet-4
        - 응답: FlowNote에 대한 구체적인 정보를 찾을 수 없어서 정확한 설명을 드리기 어렵습니다. 혹시 어떤 종류의 FlowNote(노트 앱, 소프트웨어, 서비스 등)에 대해 알고 싶으신지 좀
        - 토큰 사용: 129

    3. Claude-3.5-Haiku 테스트
    --------------------------------------------------
    ✅ 응답 성공!
        - 모델: anthropic/claude-3-5-haiku
        - 응답: 안녕하세요! 빠르게 응답해 드리겠습니다. 무엇을 도와드릴까요?
        - 토큰 사용: 73

    ==================================================
    테스트 완료!
    ==================================================

"""
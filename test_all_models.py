#━━━━━━━━━━━━━━━━━━━━━━━━━━
#test_all_models.py (완전판!)
#━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - API 테스트
3개 모델 모두 테스트
"""

from openai import OpenAI
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def test_gpt4o():
    """GPT-4o 테스트 (고성능 Chat)"""
    print("\n" + "="*50)
    print("🧪 GPT-4o 테스트")
    print("="*50)
    
    try:
        client = OpenAI(
            base_url=os.getenv("GPT4O_BASE_URL"),
            api_key=os.getenv("GPT4O_API_KEY")
        )
        
        response = client.chat.completions.create(
            model=os.getenv("GPT4O_MODEL"),
            messages=[
                {"role": "user", "content": "안녕! 간단하게 인사해줘!"}
            ],
            max_tokens=50
        )
        
        print("✅ GPT-4o: 성공!")
        print(f"응답: {response.choices[0].message.content}")
        print(f"사용 토큰: {response.usage.total_tokens}")
        return True
        
    except Exception as e:
        print(f"❌ GPT-4o: 실패!")
        print(f"오류: {e}")
        return False

def test_gpt4o_mini():
    """GPT-4o-mini 테스트 (빠른 Chat) ⭐️ 주력 모델"""
    print("\n" + "="*50)
    print("🧪 GPT-4o-mini 테스트")
    print("="*50)
    
    try:
        client = OpenAI(
            base_url=os.getenv("GPT4O_MINI_BASE_URL"),
            api_key=os.getenv("GPT4O_MINI_API_KEY")
        )
        
        response = client.chat.completions.create(
            model=os.getenv("GPT4O_MINI_MODEL"),
            messages=[
                {"role": "user", "content": "FlowNote는 무엇일까? 한 줄로 설명해줘!"}
            ],
            max_tokens=50
        )
        
        print("✅ GPT-4o-mini: 성공!")
        print(f"응답: {response.choices[0].message.content}")
        print(f"사용 토큰: {response.usage.total_tokens}")
        return True
        
    except Exception as e:
        print(f"❌ GPT-4o-mini: 실패!")
        print(f"오류: {e}")
        return False

def test_embedding():
    """Text-Embedding-3-Small 테스트 (벡터 검색) ⭐️ FAISS용"""
    print("\n" + "="*50)
    print("🧪 Text-Embedding-3-Small 테스트")
    print("="*50)
    
    try:
        client = OpenAI(
            base_url=os.getenv("EMBEDDING_BASE_URL"),
            api_key=os.getenv("EMBEDDING_API_KEY")
        )
        
        response = client.embeddings.create(
            model=os.getenv("EMBEDDING_MODEL"),
            input="FlowNote는 AI 대화를 저장하고 검색하는 도구입니다."
        )
        
        embedding_vector = response.data[0].embedding
        
        print("✅ Text-Embedding-3-Small: 성공!")
        print(f"임베딩 차원: {len(embedding_vector)}")
        print(f"처음 5개 값: {embedding_vector[:5]}")
        print(f"사용 토큰: {response.usage.total_tokens}")
        return True
        
    except Exception as e:
        print(f"❌ Text-Embedding-3-Small: 실패!")
        print(f"오류: {e}")
        return False

# ===================================
# 메인 실행
# ===================================
if __name__ == "__main__":
    print("\n" + "🚀"*25)
    print("FlowNote MVP - API 테스트 시작")
    print("🚀"*25)
    
    # 테스트 실행
    results = {
        "GPT-4o": test_gpt4o(),
        "GPT-4o-mini": test_gpt4o_mini(),
        "Text-Embedding-3-Small": test_embedding()
    }
    
    # 결과 요약
    print("\n" + "="*50)
    print("📊 테스트 결과 요약")
    print("="*50)
    
    for model, success in results.items():
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{model}: {status}")
    
    # 전체 결과
    total = len(results)
    success_count = sum(results.values())
    
    print("\n" + "="*50)
    print(f"전체: {success_count}/{total} 성공")
    print("="*50)
    
    if success_count == total:
        print("🎉 모든 API가 정상 작동합니다!")
        print("✅ FlowNote MVP 개발 준비 완료!")
    else:
        print("⚠️  일부 API에 문제가 있습니다.")
        print("🔧 .env 파일을 확인해주세요.")


""" 터미널 응답 내용

    🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀
    FlowNote MVP - API 테스트 시작
    🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀

    ==================================================
    🧪 GPT-4o 테스트
    ==================================================
    ✅ GPT-4o: 성공!
    응답: 안녕하세요! 만나서 반가워요! 😊 어떻게 도와드릴까요?
    사용 토큰: 36

    ==================================================
    🧪 GPT-4o-mini 테스트
    ==================================================
    ✅ GPT-4o-mini: 성공!
    응답: FlowNote는 사용자가 아이디어와 작업을 효율적으로 정리하고 관리할 수 있도록 돕는 디지털 노트 및 생산성 도구입니다.
    사용 토큰: 55

    ==================================================
    🧪 Text-Embedding-3-Small 테스트
    ==================================================
    ✅ Text-Embedding-3-Small: 성공!
    임베딩 차원: 1536
    처음 5개 값: [-0.04207270219922066, 0.012795306742191315, -0.04068886861205101, -0.056799180805683136, -0.0013309080386534333]
    사용 토큰: 18

    ==================================================
    📊 테스트 결과 요약
    ==================================================
    GPT-4o: ✅ 성공
    GPT-4o-mini: ✅ 성공
    Text-Embedding-3-Small: ✅ 성공

    ==================================================
    전체: 3/3 성공
    ==================================================
    🎉 모든 API가 정상 작동합니다!
    ✅ FlowNote MVP 개발 준비 완료!

"""
# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# tests/test_all_models.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - All Models Integration Test
ModelConfig 클래스 기반 (4개 모델)
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.config import ModelConfig


def test_gpt4o():
    """GPT-4o 테스트 (고성능 Chat)"""
    print("\n" + "="*60)
    print("🔵 GPT-4o 테스트")
    print("="*60)
    
    try:
        model_name = ModelConfig.GPT4O_MODEL
        client = ModelConfig.get_openai_client(model_name)
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "안녕! 간단하게 인사해줘!"}
            ],
            max_tokens=50
        )
        
        print(f"✅ GPT-4o 성공!")
        print(f"   Model: {model_name}")
        print(f"   응답: {response.choices[0].message.content}")
        print(f"   토큰: {response.usage.total_tokens}")
        return True
        
    except Exception as e:
        print(f"❌ GPT-4o 실패!")
        print(f"   오류: {e}")
        return False


def test_gpt4o_mini():
    """GPT-4o-mini 테스트 (빠른 Chat) ⭐️ 주력 모델"""
    print("\n" + "="*60)
    print("🟢 GPT-4o-mini 테스트")
    print("="*60)
    
    try:
        model_name = ModelConfig.GPT4O_MINI_MODEL
        client = ModelConfig.get_openai_client(model_name)
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "FlowNote는 무엇일까? 한 줄로 설명해줘!"}
            ],
            max_tokens=50
        )
        
        print(f"✅ GPT-4o-mini 성공!")
        print(f"   Model: {model_name}")
        print(f"   응답: {response.choices[0].message.content}")
        print(f"   토큰: {response.usage.total_tokens}")
        return True
        
    except Exception as e:
        print(f"❌ GPT-4o-mini 실패!")
        print(f"   오류: {e}")
        return False


def test_gpt41():
    """GPT-4.1 테스트 (Vision API) 🆕 새로 추가!"""
    print("\n" + "="*60)
    print("🆕 GPT-4.1 (Vision API) 테스트")
    print("="*60)
    
    try:
        model_name = ModelConfig.GPT41_MODEL
        client = ModelConfig.get_openai_client(model_name)
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "GPT-4.1이 작동하는지 확인 중이야! 한국어로 답해줘!"}
            ],
            max_tokens=50
        )
        
        print(f"✅ GPT-4.1 성공!")
        print(f"   Model: {model_name}")
        print(f"   응답: {response.choices[0].message.content}")
        print(f"   토큰: {response.usage.total_tokens}")
        return True
        
    except Exception as e:
        print(f"❌ GPT-4.1 실패!")
        print(f"   오류: {e}")
        return False


def test_embedding():
    """Text-Embedding-3-Small 테스트 (벡터 검색) ⭐️ FAISS용"""
    print("\n" + "="*60)
    print("🔷 Text-Embedding-3-Small 테스트")
    print("="*60)
    
    try:
        model_name = ModelConfig.EMBEDDING_MODEL
        client = ModelConfig.get_openai_client(model_name)
        
        response = client.embeddings.create(
            model=model_name,
            input="FlowNote는 AI 대화를 저장하고 검색하는 도구입니다."
        )
        
        embedding_vector = response.data[0].embedding
        print(f"✅ Text-Embedding-3-Small 성공!")
        print(f"   Model: {model_name}")
        print(f"   임베딩 차원: {len(embedding_vector)}")
        print(f"   처음 5개 값: {embedding_vector[:5]}")
        print(f"   토큰: {response.usage.total_tokens}")
        return True
        
    except Exception as e:
        print(f"❌ Text-Embedding-3-Small 실패!")
        print(f"   오류: {e}")
        return False


# ===================================
# 메인 실행
# ===================================

if __name__ == "__main__":
    print("\n" + "🚀"*30)
    print("FlowNote MVP - All Models Integration Test")
    print("ModelConfig 클래스 기반 (4개 모델)")
    print("🚀"*30)
    
    # 테스트 실행
    results = {
        "GPT-4o": test_gpt4o(),
        "GPT-4o-mini": test_gpt4o_mini(),
        "GPT-4.1 (Vision)": test_gpt41(),
        "Text-Embedding-3-Small": test_embedding()
    }
    
    # 결과 요약
    print("\n" + "="*60)
    print("📊 테스트 결과 요약")
    print("="*60)
    
    for model, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {model}")
    
    # 전체 결과
    total = len(results)
    success_count = sum(results.values())
    
    print("\n" + "="*60)
    print(f"전체: {success_count}/{total} 성공")
    print("="*60)
    
    if success_count == total:
        print("🎉 모든 API가 정상 작동합니다!")
        print("✅ FlowNote MVP + Vision API 개발 준비 완료!")
    else:
        print("⚠️  일부 API에 문제가 있습니다.")
        print("🔧 .env 파일과 backend/config.py를 확인해주세요.")
    
    print("\n")


"""ModelConfig 클래스 기반 (4개 모델) 테스트 결과 

    🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀
    FlowNote MVP - All Models Integration Test
    ModelConfig 클래스 기반 (4개 모델)
    🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀

    ============================================================
    🔵 GPT-4o 테스트
    ============================================================
    ✅ GPT-4o 성공!
        Model: openai/gpt-4o
        응답: 안녕하세요! 만나서 반가워요. 어떻게 도와드릴까요?
        토큰: 35

    ============================================================
    🟢 GPT-4o-mini 테스트
    ============================================================
    ✅ GPT-4o-mini 성공!
        Model: openai/gpt-4o-mini
        응답: FlowNote는 개인의 생각과 아이디어를 정리하고 공유할 수 있는 디지털 노트 관리 플랫폼입니다.
        토큰: 46

    ============================================================
    🆕 GPT-4.1 (Vision API) 테스트
    ============================================================
    ✅ GPT-4.1 성공!
        Model: openai/gpt-4.1
        응답: 네, 잘 작동하고 있습니다! 무엇을 도와드릴까요? 😊
        토큰: 46

    ============================================================
    🔷 Text-Embedding-3-Small 테스트
    ============================================================
    ✅ Text-Embedding-3-Small 성공!
        Model: text-embedding-3-small
        임베딩 차원: 1536
        처음 5개 값: [-0.042068641632795334, 0.012804398313164711, -0.04074689745903015, -0.056835003197193146, -0.0013423966011032462]
        토큰: 18

    ============================================================
    📊 테스트 결과 요약
    ============================================================
    ✅ PASS - GPT-4o
    ✅ PASS - GPT-4o-mini
    ✅ PASS - GPT-4.1 (Vision)
    ✅ PASS - Text-Embedding-3-Small

    ============================================================
    전체: 4/4 성공
    ============================================================
    🎉 모든 API가 정상 작동합니다!
    ✅ FlowNote MVP + Vision API 개발 준비 완료!

"""
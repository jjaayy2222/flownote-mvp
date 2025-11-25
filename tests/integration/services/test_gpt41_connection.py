# test_gpt41_connection.py

"""
GPT-4.1 API 기본 연결 테스트
"""

import os
from dotenv import load_dotenv
from openai import OpenAI


def test_gpt41_connection():
    """
    GPT-4.1 API 연결 테스트
    
    .env 파일에서:
    - GPT4.1_API_KEY
    - GPT4.1_BASE_URL
    - GPT4.1_MODEL
    로드해서 연결 확인
    """
    print("\n" + "="*50)
    print("🔧 GPT-4.1 API Connection Test")
    print("="*50)
    
    # 환경 변수 로드
    load_dotenv()
    
    api_key = os.getenv("GPT4.1_API_KEY")
    base_url = os.getenv("GPT4.1_BASE_URL")
    model = os.getenv("GPT4.1_MODEL")
    
    print(f"\n📋 Configuration:")
    print(f"  API Key: {'✅ Set' if api_key else '❌ Not set'}")
    print(f"  Base URL: {base_url if base_url else '❌ Not set'}")
    print(f"  Model: {model if model else '❌ Not set'}")
    
    if not all([api_key, base_url, model]):
        print("\n❌ Missing configuration in .env file")
        print("\n💡 Required in .env:")
        print("   GPT4.1_API_KEY=your_key_here")
        print("   GPT4.1_BASE_URL=your_base_url_here")
        print("   GPT4.1_MODEL=openai/gpt-4.1")
        return False
    
    try:
        # OpenAI 클라이언트 초기화
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        print("\n🔄 Testing connection...")
        print(f"   Model: {model}")
        print(f"   Endpoint: {base_url}")
        
        # 간단한 테스트 요청
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": "Say 'Hello' in one word"
                }
            ],
            max_tokens=10,
            temperature=0
        )
        
        result = response.choices[0].message.content.strip()
        
        print(f"\n✅ Connection successful!")
        print(f"   Response: '{result}'")
        print(f"   Tokens used: {response.usage.total_tokens if hasattr(response, 'usage') else 'N/A'}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Connection failed!")
        print(f"   Error: {str(e)[:200]}")
        print(f"\n💡 Troubleshooting:")
        print("   1. Check API key is correct")
        print("   2. Check base URL is correct")
        print("   3. Check model name matches API")
        print("   4. Check internet connection")
        return False


if __name__ == "__main__":
    print("\n" + "🚀" + "="*48 + "🚀")
    print("   GPT-4.1 Vision API Connection Test")
    print("🚀" + "="*48 + "🚀")
    
    success = test_gpt41_connection()
    
    print("\n" + "="*50)
    if success:
        print("🎉 Test Result: PASS")
        print("\n👉 Next step: Update backend/config.py")
    else:
        print("💔 Test Result: FAIL")
        print("\n👉 Fix .env file and try again")
    print("="*50 + "\n")
    
    exit(0 if success else 1)



"""result_1

    🚀================================================🚀
        GPT-4.1 Vision API Connection Test
    🚀================================================🚀

    ==================================================
        🔧 GPT-4.1 API Connection Test
    ==================================================

    📋 Configuration:
        API Key: ✅ Set
        Base URL: https://ml****
        Model: openai/gpt-4.1

    🔄 Testing connection...
        Model: openai/gpt-4.1
        Endpoint: https://ml***

    ✅ Connection successful!
        Response: 'Hello'
        Tokens used: 15

    ==================================================
        🎉 Test Result: PASS

        👉 Next step: Update backend/config.py
    ==================================================

"""
# tests/test_validators.py
from backend.validators import APIKeyValidator

# 테스트
valid, error = APIKeyValidator.validate_api_keys()

if valid:
    print("✅ API 키 검증 성공!")
else:
    print(f"❌ API 키 검증 실패: {error}")
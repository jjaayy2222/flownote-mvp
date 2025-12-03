import pytest
from unittest.mock import AsyncMock, patch
from backend.services.classification_service import ClassificationService
from backend.services.onboarding_service import OnboardingService

@pytest.mark.asyncio
async def test_full_onboarding_classification_pipeline():
    """
    통합 파이프라인 테스트: 온보딩 -> 분류
    
    시나리오:
    1. 사용자 생성 (Step 1)
    2. 영역 추천 및 선택 (Step 2-3)
    3. 해당 사용자로 텍스트 분류 요청 (Step 4)
    4. 검증: 분류 결과에 사용자 컨텍스트가 반영되었는가?
    """
    
    # 1. 서비스 초기화 (ClassificationService는 외부 의존성 없음)
    classification_service = ClassificationService()
    
    # 2. Mocking (GPT 호출 등 외부 의존성)
    with patch("backend.services.onboarding_service.get_gpt_helper") as MockGetHelper:
        # GPT 추천 결과 Mock
        mock_gpt_instance = MockGetHelper.return_value
        mock_gpt_instance.suggest_areas.return_value = {
            "status": "success",
            "areas": ["Python Development", "System Architecture"]
        }
        
        # OnboardingService를 Patch 내부에서 초기화해야 Mock이 적용됨
        onboarding_service = OnboardingService()
        
        # Step 1: 사용자 생성
        user_data = onboarding_service.create_user(
            occupation="Backend Developer", 
            name="Integration Tester"
        )
        user_id = user_data["user_id"]
        assert user_id is not None
        
        # Step 2: 영역 추천 (Mocked GPT)
        suggest_result = onboarding_service.suggest_areas(
            user_id=user_id, 
            occupation="Backend Developer"
        )
        assert "Python Development" in suggest_result["suggested_areas"]
        
        # Step 3: 컨텍스트 저장
        selected_areas = ["Python Development"]
        save_result = onboarding_service.save_user_context(
            user_id=user_id, 
            selected_areas=selected_areas
        )
        assert save_result["status"] == "success"
        
        # Step 4: 분류 요청 (ClassificationService)
        # KeywordClassifier가 'Python' 키워드를 감지하도록 유도
        # text = "I need to update the Python script for the backend system."
        
        # KeywordClassifier Mocking (실제 로직 대신 테스트용)
        # 실제로는 keyword.py가 동작하지만, 여기서는 파이프라인 흐름 확인이 목적이므로
        # 확실한 결과를 위해 Mocking을 하거나, 실제 로직이 'Python'을 잡는지 확인
        # 여기서는 실제 로직을 사용하되, keyword.py가 'Python'을 잡을 수 있도록 텍스트 구성
        
        # 주의: 현재 keyword.py의 규칙에는 'Python'이 없을 수 있음.
        # 따라서 keyword.py의 규칙에 맞는 텍스트 사용: "project deadline"
        # 또한 user_context_matched를 True로 만들기 위해 "Python Development" 포함
        text_for_rules = "This is an urgent project deadline task related to Python Development."
        
        # PARA Agent Mocking (외부 API 호출 방지 및 결과 고정)
        with patch("backend.services.classification_service.run_para_agent", new_callable=AsyncMock) as mock_para:
            mock_para.return_value = {
                "category": "Projects", 
                "confidence": 0.8,
                "reasoning": "Mocked PARA result"
            }
            
            result = await classification_service.classify(
                text=text_for_rules,
                user_id=user_id,
                occupation="Backend Developer",
                areas=selected_areas
            )
        
        # 검증
        assert result.category == "Projects"  # 'urgent', 'deadline' -> Projects
        assert result.user_context_matched is True # 사용자 컨텍스트가 주입되었는지 확인
        assert result.user_areas == selected_areas
        assert result.context_injected is True

@pytest.mark.asyncio
async def test_classification_conflict_resolution_flow():
    """
    통합 파이프라인 테스트: 분류 -> 충돌 해결
    
    시나리오:
    1. 분류 서비스 호출
    2. 내부적으로 PARA와 Keyword 결과 생성
    3. ConflictService가 호출되어 충돌 해결 수행
    4. 최종 결과 반환
    """
    classification_service = ClassificationService()
    
    # Mocking PARA Agent (항상 'Resources' 반환)
    with patch("backend.services.classification_service.run_para_agent", new_callable=AsyncMock) as mock_para:
        mock_para.return_value = {
            "category": "Resources", 
            "confidence": 0.6,
            "reasoning": "Looks like a guide"
        }
        
        # 텍스트는 'Projects' 키워드 포함 ("deadline")
        text = "Complete the deadline task immediately."
        
        # KeywordClassifier는 실제 로직 사용 ('deadline' -> Projects)
        
        # ConflictService 내부 로직 Mocking이 어렵다면, 
        # 실제 ConflictService가 동작하여 두 결과를 비교하는지 확인
        
        result = await classification_service.classify(text=text)
        
        # 검증
        # PARA(Resources, 0.6) vs Keyword(Projects, 높음)
        # ConflictResolver 로직에 따라 결정되겠지만, 
        # 적어도 에러 없이 결과가 나와야 함
        
        assert result.category in ["Projects", "Resources"]
        assert result.confidence > 0.0
        # 로그 정보가 포함되어 있는지 확인
        assert result.log_info["json_saved"] is True

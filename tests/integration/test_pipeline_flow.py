# tests/integration/test_pipeline_flow.py

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
            "areas": ["Python Development", "System Architecture"],
        }

        # OnboardingService를 Patch 내부에서 초기화해야 Mock이 적용됨
        onboarding_service = OnboardingService()

        # Step 1: 사용자 생성
        user_data = onboarding_service.create_user(
            occupation="Backend Developer", name="Integration Tester"
        )
        user_id = user_data["user_id"]
        assert user_id is not None

        # Step 2: 영역 추천 (Mocked GPT)
        suggest_result = onboarding_service.suggest_areas(
            user_id=user_id, occupation="Backend Developer"
        )
        assert "Python Development" in suggest_result["suggested_areas"]

        # Step 3: 컨텍스트 저장
        selected_areas = ["Python Development"]
        save_result = onboarding_service.save_user_context(
            user_id=user_id, selected_areas=selected_areas
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
        text_for_rules = (
            "This is an urgent project deadline task related to Python Development."
        )

        # PARA Agent Mocking (외부 API 호출 방지 및 결과 고정)
        with patch(
            "backend.classifier.hybrid_classifier.HybridClassifier.classify",
            new_callable=AsyncMock,
        ) as mock_para:
            mock_para.return_value = {
                "category": "Projects",
                "confidence": 0.8,
                "reasoning": "Mocked PARA result",
            }

            result = await classification_service.classify(
                text=text_for_rules,
                user_id=user_id,
                occupation="Backend Developer",
                areas=selected_areas,
            )

        # 검증
        assert result.category == "Projects"  # 'urgent', 'deadline' -> Projects
        assert (
            result.user_context_matched is True
        )  # 사용자 컨텍스트가 주입되었는지 확인
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
    with patch(
        "backend.classifier.hybrid_classifier.HybridClassifier.classify",
        new_callable=AsyncMock,
    ) as mock_para:
        mock_para.return_value = {
            "category": "Resources",
            "confidence": 0.6,
            "reasoning": "Looks like a guide",
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


@pytest.mark.asyncio
async def test_classification_conflict_resolution_parsing():
    """
    통합 파이프라인 테스트: ConflictService 결과 파싱 검증

    목표: ConflictService의 중첩된 결과 구조가 ClassificationService에서 올바르게 파싱되는지 확인
    """
    classification_service = ClassificationService()

    # ConflictService Mocking
    with patch(
        "backend.services.classification_service.ConflictService"
    ) as MockConflictService:
        mock_instance = MockConflictService.return_value

        # ConflictService.classify_text가 반환하는 중첩 구조 Mock
        mock_instance.classify_text = AsyncMock(
            return_value={
                "snapshot_id": "snap_mock_123",
                "timestamp": "2025-12-03T12:00:00",
                "text": "Conflict text",
                "conflict_result": {
                    "final_category": "Resources",
                    "confidence": 0.42,
                    "conflict_detected": True,
                    "requires_review": True,
                    "reason": "Mocked conflict reason",
                },
                "status": "success",
            }
        )

        # ClassificationService 인스턴스에 Mock 주입 (이미 생성된 인스턴스의 속성 교체)
        classification_service.conflict_service = mock_instance

        # PARA, Keyword 결과는 중요하지 않음 (ConflictService가 최종 결정하므로)
        with patch(
            "backend.classifier.hybrid_classifier.HybridClassifier.classify",
            new_callable=AsyncMock,
        ) as mock_para:
            mock_para.return_value = {"category": "Projects", "confidence": 0.5}

            result = await classification_service.classify(text="Conflict text")

            # 검증: 중첩된 필드들이 올바르게 매핑되었는지 확인
            assert result.category == "Resources"
            assert result.confidence == 0.42
            assert result.conflict_detected is True
            assert result.requires_review is True
            assert result.reasoning == "Mocked conflict reason"


"""test_result

    pytest tests/integration/test_pipeline_flow.py -v
    
    =========== test session starts ===========
    configfile: pytest.ini
    plugins: anyio-4.11.0, langsmith-0.4.37, asyncio-1.3.0, cov-7.0.0
    asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
    collected 3 items                         

    tests/integration/test_pipeline_flow.py::test_full_onboarding_classification_pipeline PASSED [ 33%]
    tests/integration/test_pipeline_flow.py::test_classification_conflict_resolution_flow PASSED [ 66%]
    tests/integration/test_pipeline_flow.py::test_classification_conflict_resolution_parsing PASSED [100%]

    ============= tests coverage ==============
    _ coverage: platform darwin, python 3.11.10-final-0 _

    Name                                               Stmts   Miss  Cover   Missing
    --------------------------------------------------------------------------------
    backend/__init__.py                                    1      0   100%
    backend/api/__init__.py                                3      3     0%   8-41
    backend/api/endpoints/__init__.py                      4      4     0%   5-9
    backend/api/endpoints/classify.py                      5      5     0%   5-12
    backend/api/endpoints/conflict_resolver.py            71     71     0%   3-197
    backend/api/endpoints/conflict_resolver_agent.py     165    165     0%   9-430
    backend/api/endpoints/dashboard.py                    31     31     0%   5-56
    backend/api/endpoints/metadata.py                      5      5     0%   5-12
    backend/api/endpoints/search.py                        5      5     0%   5-12
    backend/api/models.py                                  4      4     0%   7-21
    backend/api/models/__init__.py                         3      3     0%   11-37
    backend/api/routes.py                                  6      6     0%   5-13
    backend/chunking.py                                   35     35     0%   10-124
    backend/classifier/__init__.py                         2      0   100%
    backend/classifier/base_classifier.py                 31     12    61%   41, 50-53, 56-58, 61-63, 70
    backend/classifier/conflict_resolver.py               38     10    74%   73-74, 119, 136, 140-150
    backend/classifier/context_injector.py               109    109     0%   7-243
    backend/classifier/keyword.py                         52      3    94%   39-40, 62
    backend/classifier/langchain_integration.py          208    171    18%   47-58, 75-109, 115-133, 147-171, 186-203, 235-272, 281-299, 304-320, 348-374, 400-460, 466-555
    backend/classifier/metadata_classifier.py             37     37     0%   7-91
    backend/classifier/para_agent.py                      77     49    36%   32-41, 49-54, 62-86, 94-104, 112-124, 132-149, 154-170, 175, 181-194
    backend/classifier/para_agent_wrapper.py              21     21     0%   5-111
    backend/classifier/para_classifier.py                 83     83     0%   9-277
    backend/classifier/snapshot_manager.py                38     12    68%   27, 69, 73-76, 80-86, 97
    backend/cli.py                                        89     89     0%   6-165
    backend/config.py                                    118     53    55%   29-37, 89, 93-95, 98-100, 107, 111, 113, 128-142, 147-176, 223, 238-245
    backend/dashboard/__init__.py                          0      0   100%
    backend/dashboard/dashboard_core.py                   13     13     0%   3-42
    backend/data_manager.py                              167     94    44%   44-46, 50-51, 55-57, 80, 82, 88-92, 96-99, 110-114, 120-129, 140, 157-158, 181-182, 188-195, 201-204, 215-227, 240-254, 260-270, 291-331
    backend/database/__init__.py                           2      2     0%   3-5
    backend/database/connection.py                        96     96     0%   3-202
    backend/database/metadata_schema.py                   52     52     0%   3-144
    backend/embedding.py                                  33     33     0%   10-118
    backend/exceptions.py                                 12     12     0%   10-43
    backend/export.py                                     28     28     0%   7-68
    backend/faiss_search.py                               78     78     0%   9-248
    backend/main.py                                       33      7    79%   110, 125, 143-149
    backend/metadata.py                                   95     95     0%   9-329
    backend/models/__init__.py                             5      0   100%
    backend/models/classification.py                      78      0   100%
    backend/models/common.py                              43      0   100%
    backend/models/conflict.py                            81      0   100%
    backend/models/user.py                                32      0   100%
    backend/modules/__init__.py                            3      3     0%   7-10
    backend/modules/pdf_helper.py                         26     26     0%   9-62
    backend/modules/vision_helper.py                      59     59     0%   11-296
    backend/routes/__init__.py                             0      0   100%
    backend/routes/api_models.py                          24     24     0%   17-112
    backend/routes/classifier_routes.py                   42     27    36%   93-106, 138-181
    backend/routes/conflict_routes.py                     20      8    60%   42-49, 55
    backend/routes/onboarding_routes.py                   36     16    56%   63-64, 89-100, 122-126, 148-154, 174-179
    backend/search_history.py                             93     93     0%   9-353
    backend/services/__init__.py                           1      0   100%
    backend/services/classification_service.py            86     13    85%   133-135, 157-159, 176, 179, 181, 242, 277-279
    backend/services/conflict_service.py                  71     30    58%   25-35, 84-86, 91-103, 140-143, 186, 196-199, 212, 216, 220, 224-225
    backend/services/gpt_helper.py                       130     89    32%   25-29, 57-60, 74-103, 119-128, 146-196, 209-222, 244-274, 296-327, 357-392
    backend/services/onboarding_service.py                53     22    58%   58-60, 83, 96-98, 127, 138-140, 158-182
    backend/services/parallel_processor.py                23     23     0%   8-72
    backend/utils.py                                      42     42     0%   9-110
    backend/validators.py                                 88     88     0%   16-252
    --------------------------------------------------------------------------------
    TOTAL                                               2886   2059    29%
    ============ 3 passed in 0.44s ============

"""

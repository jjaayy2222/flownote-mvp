# tests/e2e/test_full_flow.py

import pytest
import io
import uuid
from unittest.mock import patch, AsyncMock


def _perform_onboarding_step1(client, user_name):
    """온보딩 Step 1: 사용자 생성"""
    response = client.post(
        "/onboarding/step1", json={"name": user_name, "occupation": "Developer"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    return data["user_id"]


def _perform_onboarding_step2(client, user_id):
    """온보딩 Step 2: 영역 추천"""
    response = client.get(
        "/onboarding/suggest-areas",
        params={"user_id": user_id, "occupation": "Developer"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["suggested_areas"]) > 0
    return data["suggested_areas"]


def _perform_onboarding_step3(client, user_id, selected_areas):
    """온보딩 Step 3: 컨텍스트 저장"""
    response = client.post(
        "/onboarding/save-context",
        json={"user_id": user_id, "selected_areas": selected_areas},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def _perform_file_classification(client, user_id):
    """파일 분류 (Mocking 적용)"""
    mock_para_result = {"category": "Projects", "confidence": 0.9}
    mock_keyword_result = {"tags": ["python"], "confidence": 0.8}

    # ClassificationService 내부의 외부 호출 Mocking
    with patch(
        "backend.classifier.hybrid_classifier.HybridClassifier.classify",
        new_callable=AsyncMock,
    ) as mock_para:
        mock_para.return_value = mock_para_result

        # KeywordClassifier Mocking (인스턴스 메서드)
        with patch(
            "backend.classifier.keyword.KeywordClassifier.classify",
            new_callable=AsyncMock,
        ) as mock_keyword:
            mock_keyword.return_value = mock_keyword_result

            # 파일 업로드
            file_content = "This is a test project file."
            files = {
                "file": (
                    "test.txt",
                    io.BytesIO(file_content.encode("utf-8")),
                    "text/plain",
                )
            }

            response = client.post(
                "/classifier/file", files=files, data={"user_id": user_id}
            )

            assert response.status_code == 200
            result = response.json()

            assert result["category"] == "Projects"
            # ConflictResolver 로직에 따라 달라질 수 있으므로 범위 체크
            assert 0.0 <= result["confidence"] <= 1.0
            assert "keyword_tags" in result


@patch("backend.services.gpt_helper.GPT4oHelper.suggest_areas")
def test_full_onboarding_and_classification_flow(mock_suggest, client):
    # Mock 설정
    mock_suggest.return_value = {
        "status": "success",
        "areas": ["Python", "AI", "Web"],
        "message": "Mocked response",
    }
    """
    E2E 테스트: 온보딩 -> 분류 전체 흐름 검증
    """
    # 1. 온보딩 Step 1: 사용자 생성
    user_name = f"User_{uuid.uuid4().hex[:6]}"
    user_id = _perform_onboarding_step1(client, user_name)

    # 2. 온보딩 Step 2: 영역 추천
    suggested_areas = _perform_onboarding_step2(client, user_id)

    # 3. 온보딩 Step 3: 컨텍스트 저장
    selected_areas = suggested_areas[:3]
    _perform_onboarding_step3(client, user_id, selected_areas)

    # 4. 파일 분류
    _perform_file_classification(client, user_id)


"""수정 후 test_result 

pytest tests/e2e/test_full_flow.py -vv

============================= test session starts ==============================
platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
cachedir: .pytest_cache
configfile: pytest.ini
plugins: anyio-4.11.0, langsmith-0.4.37, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/e2e/test_full_flow.py::test_full_onboarding_and_classification_flow PASSED [100%]

================================ tests coverage ================================
______________ coverage: platform darwin, python 3.11.10-final-0 _______________

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
backend/classifier/conflict_resolver.py               38     10    74%   73-74, 119, 136, 140-150
backend/classifier/context_injector.py               109    109     0%   7-243
backend/classifier/keyword_classifier.py             309    230    26%   66-77, 123, 135-137, 151, 177-182, 226-242, 265-467, 477-528, 532-553, 561-615, 629-664, 668, 683, 698-752
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
backend/main.py                                       33      7    79%   80, 95, 113-119
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
backend/routes/api_models.py                          22     22     0%   18-75
backend/routes/classifier_routes.py                   40     16    60%   83-96, 131-134, 138-141, 158-160
backend/routes/conflict_routes.py                     20      8    60%   42-49, 55
backend/routes/onboarding_routes.py                   32      7    78%   57, 80, 100, 115-120
backend/search_history.py                             93     93     0%   9-353
backend/services/__init__.py                           0      0   100%
backend/services/classification_service.py            81     12    85%   128-130, 152-154, 168, 170, 227, 262-264
backend/services/conflict_service.py                  71     30    58%   25-35, 84-86, 91-103, 140-143, 186, 196-199, 212, 216, 220, 224-225
backend/services/gpt_helper.py                       130     63    52%   25-29, 57-60, 75, 124-125, 152-153, 185-196, 209-222, 244-274, 296-327, 357-392
backend/services/onboarding_service.py                53     22    58%   58-60, 83, 96-98, 127, 138-140, 158-182
backend/services/parallel_processor.py                23     23     0%   8-72
backend/utils.py                                      42     42     0%   9-110
backend/validators.py                                 88     88     0%   16-252
--------------------------------------------------------------------------------
TOTAL                                               3098   2225    28%
============================== 1 passed in 2.07s ===============================

"""

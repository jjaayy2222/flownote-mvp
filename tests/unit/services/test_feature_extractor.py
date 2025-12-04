# tests/unit/services/test_feature_extractor.py

import pytest
from backend.services.feature_extractor import FeatureExtractor, FileFeatures

@pytest.fixture
def extractor():
    return FeatureExtractor()

@pytest.mark.asyncio
async def test_extract_basic_features(extractor):
    """기본 텍스트 및 구조 특징 추출 테스트"""
    content = """
    # Project Plan
    This is an urgent task.
    - [ ] Todo item 1
    - [x] Todo item 2
    
    Deadline: 2025-12-31
    """
    metadata = {"tags": ["work", "important"], "reference_count": 2}
    usage = {"access_count": 10, "days_since_access": 1}
    
    features = await extractor.extract(content, metadata, usage)
    
    # 텍스트 분석
    assert features.text_length > 0
    assert features.word_count > 0
    
    # 구조 분석
    assert features.has_checklist is True
    assert features.has_deadline is True
    assert features.has_code_block is False
    
    # 관계 분석
    assert features.tag_count == 2
    assert features.reference_count == 2
    
    # 긴급성 분석
    assert "urgent" in features.urgency_indicators
    assert "deadline" in features.urgency_indicators

@pytest.mark.asyncio
async def test_extract_empty_content(extractor):
    """빈 콘텐츠 처리 테스트"""
    features = await extractor.extract("", {}, {})
    
    assert features.text_length == 0
    assert features.word_count == 0
    assert features.has_checklist is False
    assert features.sentiment_score == 0.0

@pytest.mark.asyncio
async def test_extract_temporal_features(extractor):
    """시간 특징 계산 테스트"""
    usage = {
        "access_count": 10,
        "days_since_access": 4,  # 빈도 = 10 / 5 = 2.0
        "edit_count": 5,
        "days_since_edit": 9     # 빈도 = 5 / 10 = 0.5
    }
    
    features = await extractor.extract("test", {}, usage)
    
    assert features.days_since_access == 4
    assert features.access_frequency == 2.0
    assert features.edit_frequency == 0.5

@pytest.mark.asyncio
async def test_extract_sentiment(extractor):
    """감정 분석 테스트"""
    positive_text = "Great job! Success is near."
    negative_text = "This is a terrible bug and failure."
    
    pos_features = await extractor.extract(positive_text, {}, {})
    neg_features = await extractor.extract(negative_text, {}, {})
    
    assert pos_features.sentiment_score > 0
    assert neg_features.sentiment_score < 0

@pytest.mark.asyncio
async def test_extract_code_block(extractor):
    """코드 블록 감지 테스트"""
    content = """
    Here is some code:
    ```python
    print("Hello")
    ```
    """
    features = await extractor.extract(content, {}, {})
    assert features.has_code_block is True


"""test_result

    pytest tests/unit/services/test_feature_extractor.py -v
    
    ============================= test session starts ==============================
    platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
    cachedir: .pytest_cache
    configfile: pytest.ini
    plugins: anyio-4.11.0, langsmith-0.4.37, asyncio-1.3.0, cov-7.0.0
    asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
    collecting ... collected 5 items

    tests/unit/services/test_feature_extractor.py::test_extract_basic_features PASSED [ 20%]
    tests/unit/services/test_feature_extractor.py::test_extract_empty_content PASSED [ 40%]
    tests/unit/services/test_feature_extractor.py::test_extract_temporal_features PASSED [ 60%]
    tests/unit/services/test_feature_extractor.py::test_extract_sentiment PASSED [ 80%]
    tests/unit/services/test_feature_extractor.py::test_extract_code_block PASSED [100%]

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
    backend/classifier/base_classifier.py                 31     19    39%   41, 47-66, 70
    backend/classifier/conflict_resolver.py               38     21    45%   40-42, 68-111, 119, 128-136, 140-150
    backend/classifier/context_injector.py               109    109     0%   7-243
    backend/classifier/keyword.py                         52     40    23%   30-47, 54-94, 108
    backend/classifier/langchain_integration.py          208    171    18%   47-58, 75-109, 115-133, 147-171, 186-203, 235-272, 281-299, 304-320, 348-374, 400-460, 466-555
    backend/classifier/metadata_classifier.py             37     37     0%   7-91
    backend/classifier/para_agent.py                      77     49    36%   32-41, 49-54, 62-86, 94-104, 112-124, 132-149, 154-170, 175, 181-194
    backend/classifier/para_agent_wrapper.py              21     21     0%   5-111
    backend/classifier/para_classifier.py                 83     83     0%   9-277
    backend/classifier/snapshot_manager.py                38     15    61%   27, 50-65, 69, 73-76, 80-86, 97
    backend/cli.py                                        89     89     0%   6-165
    backend/config.py                                    118     53    55%   29-37, 89, 93-95, 98-100, 107, 111, 113, 128-142, 147-176, 223, 238-245
    backend/dashboard/__init__.py                          0      0   100%
    backend/dashboard/dashboard_core.py                   13     13     0%   3-42
    backend/data_manager.py                              167    132    21%   44-46, 50-51, 55-57, 73-114, 120-129, 135-158, 168-182, 188-195, 201-204, 215-227, 240-254, 260-270, 291-331
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
    backend/services/classification_service.py            90     67    26%   74-139, 144, 157-163, 171-193, 199-206, 218-283
    backend/services/conflict_service.py                  74     51    31%   25-35, 78-143, 161-204, 217, 221, 225, 229-230
    backend/services/feature_extractor.py                 79      5    94%   42, 95-97, 203
    backend/services/gpt_helper.py                       130     89    32%   25-29, 57-60, 74-103, 119-128, 146-196, 209-222, 244-274, 296-327, 357-392
    backend/services/onboarding_service.py                53     39    26%   38-60, 78-98, 113-140, 158-182
    backend/services/parallel_processor.py                23     23     0%   8-72
    backend/utils.py                                      42     42     0%   9-110
    backend/validators.py                                 88     88     0%   16-252
    --------------------------------------------------------------------------------
    TOTAL                                               2972   2252    24%
    ============================== 5 passed in 1.50s ===============================

"""
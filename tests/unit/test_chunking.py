# tests/unit/test_chunking.py

import pytest
from backend.chunking import TextChunker


def test_text_chunker_init():
    """TextChunker 초기화 테스트"""
    chunker = TextChunker()
    assert chunker.chunk_size == 500
    assert chunker.chunk_overlap == 50


def test_text_chunker_custom_init():
    """TextChunker 커스텀 초기화 테스트"""
    chunker = TextChunker(chunk_size=100, chunk_overlap=20)
    assert chunker.chunk_size == 100
    assert chunker.chunk_overlap == 20


def test_chunk_text_empty():
    """빈 텍스트 청킹 테스트"""
    chunker = TextChunker()
    chunks = chunker.chunk_text("")
    assert chunks == []


def test_chunk_text_short():
    """짧은 텍스트 청킹 테스트"""
    chunker = TextChunker(chunk_size=100)
    text = "Short text"
    chunks = chunker.chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_long():
    """긴 텍스트 청킹 테스트"""
    chunker = TextChunker(chunk_size=10, chunk_overlap=2)
    text = "A" * 30
    chunks = chunker.chunk_text(text)
    assert len(chunks) == 4
    assert len(chunks[0]) == 10


def test_chunk_with_metadata_success():
    """메타데이터 포함 청킹 테스트"""
    chunker = TextChunker(chunk_size=10, chunk_overlap=2)
    text = "A" * 30
    metadata = {"source": "test.txt"}
    chunks = chunker.chunk_with_metadata(text, metadata)

    assert len(chunks) == 4
    assert chunks[0]["metadata"] == metadata
    assert chunks[0]["chunk_index"] == 0


""" 수정 후 test_result

pytest tests/unit/test_chunking.py -vv --cov=backend.chunking --cov-report=term-missing

============================= test session starts ==============================
platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
cachedir: .pytest_cache
configfile: pytest.ini
plugins: anyio-4.11.0, langsmith-0.4.37, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 8 items

tests/unit/test_chunking.py::test_text_chunker_init PASSED               [ 12%]
tests/unit/test_chunking.py::test_text_chunker_custom_init PASSED        [ 25%]
tests/unit/test_chunking.py::test_chunk_text_empty PASSED                [ 37%]
tests/unit/test_chunking.py::test_chunk_text_short PASSED                [ 50%]
tests/unit/test_chunking.py::test_chunk_text_long PASSED                 [ 62%]
tests/unit/test_chunking.py::test_chunk_with_metadata_empty PASSED       [ 75%]
tests/unit/test_chunking.py::test_chunk_with_metadata_success PASSED     [ 87%]
tests/unit/test_chunking.py::test_chunk_with_metadata_no_metadata 

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
/Users/jay/ICT-projects/flownote-mvp/backend/chunking.py:26: KeyboardInterrupt
(to show a full traceback on KeyboardInterrupt use --full-trace)
============================== 7 passed in 42.63s ==============================

pytest tests/unit/test_chunking.py -vv --cov=backend.chunking --cov-report=term

============================= test session starts ==============================
platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
cachedir: .pytest_cache
rootdir: /Users/jay/ICT-projects/flownote-mvp
configfile: pytest.ini
plugins: anyio-4.11.0, langsmith-0.4.37, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 6 items

tests/unit/test_chunking.py::test_text_chunker_init PASSED               [ 16%]
tests/unit/test_chunking.py::test_text_chunker_custom_init PASSED        [ 33%]
tests/unit/test_chunking.py::test_chunk_text_empty PASSED                [ 50%]
tests/unit/test_chunking.py::test_chunk_text_short PASSED                [ 66%]
tests/unit/test_chunking.py::test_chunk_text_long PASSED                 [ 83%]
tests/unit/test_chunking.py::test_chunk_with_metadata_success PASSED     [100%]

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
backend/chunking.py                                   35     12    66%   50-66
backend/classifier/__init__.py                         2      0   100%
backend/classifier/conflict_resolver.py               38     21    45%   40-42, 68-111, 119, 128-136, 140-150
backend/classifier/context_injector.py               109    109     0%   7-243
backend/classifier/keyword_classifier.py             309    230    26%   66-77, 123, 135-137, 151, 177-182, 226-242, 265-467, 477-528, 532-553, 561-615, 629-664, 668, 683, 698-752
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
backend/routes/classifier_routes.py                   40     25    38%   83-96, 119-160
backend/routes/conflict_routes.py                     20      8    60%   42-49, 55
backend/routes/onboarding_routes.py                   32     17    47%   52-64, 77-82, 95-102, 115-120
backend/search_history.py                             93     93     0%   9-353
backend/services/__init__.py                           0      0   100%
backend/services/classification_service.py            81     58    28%   72-130, 135, 148-154, 162-174, 180-187, 199-264
backend/services/conflict_service.py                  71     48    32%   25-35, 78-143, 161-199, 212, 216, 220, 224-225
backend/services/gpt_helper.py                       130     89    32%   25-29, 57-60, 74-103, 119-128, 146-196, 209-222, 244-274, 296-327, 357-392
backend/services/onboarding_service.py                53     39    26%   38-60, 78-98, 113-140, 158-182
backend/services/parallel_processor.py                23     23     0%   8-72
backend/utils.py                                      42     42     0%   9-110
backend/validators.py                                 88     88     0%   16-252
--------------------------------------------------------------------------------
TOTAL                                               3098   2380    23%
============================== 6 passed in 0.39s ===============================

"""

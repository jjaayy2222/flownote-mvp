# tests/unit/test_validators.py

import pytest
import os
from backend.validators import ValidationError, FileValidator, QueryValidator


# FileValidator 테스트
class TestFileValidator:
    def test_init_default_values(self):
        """FileValidator 기본값 초기화 테스트"""
        validator = FileValidator()
        assert validator.max_file_size_mb == 200
        assert validator.max_file_size_bytes == 200 * 1024 * 1024
        assert validator.allowed_extensions == [".pdf", ".txt", ".md"]

    def test_init_custom_values(self):
        """FileValidator 커스텀 값 초기화 테스트"""
        validator = FileValidator(max_file_size_mb=100, allowed_extensions=[".docx"])
        assert validator.max_file_size_mb == 100
        assert validator.allowed_extensions == [".docx"]

    def test_validate_file_size_empty_file(self, tmp_path):
        """빈 파일 검증 테스트"""
        validator = FileValidator()
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        valid, error = validator.validate_file_size(str(empty_file))
        assert not valid
        assert "빈 파일" in error

    def test_validate_file_size_too_large(self, tmp_path):
        """파일 크기 초과 검증 테스트"""
        validator = FileValidator(max_file_size_mb=1)
        large_file = tmp_path / "large.txt"
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB

        valid, error = validator.validate_file_size(str(large_file))
        assert not valid
        assert "너무 큽니다" in error

    def test_validate_file_size_valid(self, tmp_path):
        """정상 파일 크기 검증 테스트"""
        validator = FileValidator()
        valid_file = tmp_path / "valid.txt"
        valid_file.write_text("Valid content")

        valid, error = validator.validate_file_size(str(valid_file))
        assert valid
        assert error is None

    def test_validate_extension_invalid(self):
        """잘못된 확장자 검증 테스트"""
        validator = FileValidator()
        valid, error = validator.validate_extension("test.docx")
        assert not valid
        assert "지원하지 않는 파일 형식" in error

    def test_validate_extension_valid(self):
        """정상 확장자 검증 테스트"""
        validator = FileValidator()
        valid, error = validator.validate_extension("test.pdf")
        assert valid
        assert error is None

    def test_validate_file_not_exists(self):
        """존재하지 않는 파일 검증 테스트"""
        validator = FileValidator()
        valid, error = validator.validate_file("nonexistent.txt")
        assert not valid
        assert "존재하지 않습니다" in error

    def test_validate_file_success(self, tmp_path):
        """전체 파일 검증 성공 테스트"""
        validator = FileValidator()
        valid_file = tmp_path / "valid.pdf"
        valid_file.write_text("Valid PDF content")

        valid, error = validator.validate_file(str(valid_file))
        assert valid
        assert error is None


# QueryValidator 테스트
class TestQueryValidator:
    def test_init_default_values(self):
        """QueryValidator 기본값 초기화 테스트"""
        validator = QueryValidator()
        assert validator.min_length == 2
        assert validator.max_length == 500

    def test_validate_query_empty(self):
        """빈 쿼리 검증 테스트"""
        validator = QueryValidator()
        valid, error = validator.validate_query("")
        assert not valid
        assert "검색어를 입력해주세요" in error

    def test_validate_query_none(self):
        """None 쿼리 검증 테스트"""
        validator = QueryValidator()
        valid, error = validator.validate_query(None)
        assert not valid
        assert "검색어를 입력해주세요" in error

    def test_validate_query_whitespace_only(self):
        """공백만 있는 쿼리 검증 테스트"""
        validator = QueryValidator()
        valid, error = validator.validate_query("   ")
        assert not valid
        # strip() 후 빈 문자열이 되므로 첫 번째 체크에 걸림
        assert "검색어를 입력해주세요" in error

    def test_validate_query_too_short(self):
        """너무 짧은 쿼리 검증 테스트"""
        validator = QueryValidator(min_length=5)
        valid, error = validator.validate_query("abc")
        assert not valid
        assert "너무 짧습니다" in error

    def test_validate_query_too_long(self):
        """너무 긴 쿼리 검증 테스트"""
        validator = QueryValidator(max_length=10)
        valid, error = validator.validate_query("a" * 20)
        assert not valid
        assert "너무 깁니다" in error

    def test_validate_query_valid(self):
        """정상 쿼리 검증 테스트"""
        validator = QueryValidator()
        valid, error = validator.validate_query("Valid query")
        assert valid
        assert error is None


"""수정 후 test_result

pytest tests/unit/test_validators.py tests/unit/test_utils.py -vv --cov=backend.validators --cov=backend.utils --cov-report=term-missing

<truncated 2 lines>
cachedir: .pytest_cache
rootdir: /Users/jay/ICT-projects/flownote-mvp
configfile: pytest.ini
plugins: anyio-4.11.0, langsmith-0.4.37, asyncio-1.3.0, cov-7.0.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collecting ... collected 22 items

tests/unit/test_validators.py::TestFileValidator::test_init_default_values PASSED [  4%]
tests/unit/test_validators.py::TestFileValidator::test_init_custom_values PASSED [  9%]
tests/unit/test_validators.py::TestFileValidator::test_validate_file_size_empty_file PASSED [ 13%]
tests/unit/test_validators.py::TestFileValidator::test_validate_file_size_too_large PASSED [ 18%]
tests/unit/test_validators.py::TestFileValidator::test_validate_file_size_valid PASSED [ 22%]
tests/unit/test_validators.py::TestFileValidator::test_validate_extension_invalid PASSED [ 27%]
tests/unit/test_validators.py::TestFileValidator::test_validate_extension_valid PASSED [ 31%]
tests/unit/test_validators.py::TestFileValidator::test_validate_file_not_exists PASSED [ 36%]
tests/unit/test_validators.py::TestFileValidator::test_validate_file_success PASSED [ 40%]
tests/unit/test_validators.py::TestQueryValidator::test_init_default_values PASSED [ 45%]
tests/unit/test_validators.py::TestQueryValidator::test_validate_query_empty PASSED [ 50%]
tests/unit/test_validators.py::TestQueryValidator::test_validate_query_none PASSED [ 54%]
tests/unit/test_validators.py::TestQueryValidator::test_validate_query_whitespace_only PASSED [ 59%]
tests/unit/test_validators.py::TestQueryValidator::test_validate_query_too_short PASSED [ 63%]
tests/unit/test_validators.py::TestQueryValidator::test_validate_query_too_long PASSED [ 68%]
tests/unit/test_validators.py::TestQueryValidator::test_validate_query_valid PASSED [ 72%]
tests/unit/test_utils.py::test_count_tokens PASSED                       [ 77%]
tests/unit/test_utils.py::test_read_file_content PASSED                  [ 81%]
tests/unit/test_utils.py::test_format_file_size PASSED                   [ 86%]
tests/unit/test_utils.py::test_estimate_cost PASSED                      [ 90%]
tests/unit/test_utils.py::test_load_pdf PASSED                           [ 95%]
tests/unit/test_utils.py::test_save_to_markdown PASSED                   [100%]

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
backend/utils.py                                      42      0   100%
backend/validators.py                                 88     36    59%   68-69, 108, 113, 150, 178-229, 240-252
--------------------------------------------------------------------------------
TOTAL                                               3098   2309    25%
============================== 22 passed in 1.33s ==============================

"""

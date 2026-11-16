# tests/unit/test_exceptions.py

"""
[KO] backend/exceptions.py 커스텀 예외 계층에 대한 단위 테스트.
[EN] Unit tests for the custom exception hierarchy in backend/exceptions.py.
"""

import pytest

from backend.exceptions import (
    APIKeyError,
    ConfigurationError,
    EmbeddingError,
    FileValidationError,
    FlowNoteError,
    QueryValidationError,
    SearchError,
)


class TestFlowNoteErrorHierarchy:
    """최상위 기본 예외 클래스 및 상속 구조를 검증합니다."""

    def test_flownote_error_is_base_exception(self):
        exc = FlowNoteError("base error")
        assert isinstance(exc, Exception)
        assert str(exc) == "base error"

    def test_file_validation_error_inherits_flownote_error(self):
        exc = FileValidationError("invalid extension")
        assert isinstance(exc, FlowNoteError)
        assert isinstance(exc, Exception)
        assert str(exc) == "invalid extension"

    def test_query_validation_error_inherits_flownote_error(self):
        exc = QueryValidationError("query too short")
        assert isinstance(exc, FlowNoteError)
        assert str(exc) == "query too short"

    def test_api_key_error_inherits_flownote_error(self):
        exc = APIKeyError("API key not set")
        assert isinstance(exc, FlowNoteError)
        assert str(exc) == "API key not set"

    def test_configuration_error_inherits_flownote_error(self):
        exc = ConfigurationError("missing required config")
        assert isinstance(exc, FlowNoteError)
        assert str(exc) == "missing required config"

    def test_search_error_inherits_flownote_error(self):
        exc = SearchError("index lookup failed")
        assert isinstance(exc, FlowNoteError)
        assert str(exc) == "index lookup failed"


class TestEmbeddingError:
    """EmbeddingError의 초기화 및 error_type 필드를 검증합니다."""

    def test_default_error_type_is_api_error(self):
        exc = EmbeddingError("embedding failed")
        assert exc.error_type == "api_error"
        assert str(exc) == "embedding failed"

    def test_explicit_error_type_timeout(self):
        exc = EmbeddingError("timed out", error_type="timeout")
        assert exc.error_type == "timeout"

    def test_explicit_error_type_connection(self):
        exc = EmbeddingError("connection refused", error_type="connection")
        assert exc.error_type == "connection"

    def test_explicit_error_type_rate_limit(self):
        exc = EmbeddingError("rate limit exceeded", error_type="rate_limit")
        assert exc.error_type == "rate_limit"

    def test_empty_message_allowed(self):
        exc = EmbeddingError()
        assert not str(exc)
        assert exc.error_type == "api_error"

    def test_embedding_error_inherits_flownote_error(self):
        exc = EmbeddingError("fail")
        assert isinstance(exc, FlowNoteError)
        assert isinstance(exc, Exception)


class TestExceptionRaising:
    """raise 문으로 올바르게 발생하고 catch 되는지 검증합니다."""

    def test_raise_and_catch_file_validation_error(self):
        with pytest.raises(FileValidationError, match="unsupported extension"):
            raise FileValidationError("unsupported extension")

    def test_raise_and_catch_query_validation_error(self):
        with pytest.raises(QueryValidationError, match="whitespace only"):
            raise QueryValidationError("whitespace only")

    def test_raise_and_catch_as_base_flownote_error(self):
        """서브클래스를 FlowNoteError로 catch 가능해야 합니다."""
        with pytest.raises(FlowNoteError):
            raise APIKeyError("key missing")

    def test_raise_embedding_error_with_type(self):
        with pytest.raises(EmbeddingError) as exc_info:
            raise EmbeddingError("rate limited", error_type="rate_limit")
        assert exc_info.value.error_type == "rate_limit"
        assert str(exc_info.value) == "rate limited"

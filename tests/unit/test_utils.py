# tests/unit/test_utils.py

from unittest.mock import MagicMock, mock_open, patch

import pytest

from backend.utils import (
    count_tokens,
    estimate_cost,
    format_file_size,
    load_pdf,
    read_file_content,
    save_to_markdown,
)


def test_count_tokens():
    """count_tokens 함수 테스트"""
    text = "Hello World"
    # tiktoken이 설치되어 있다고 가정
    assert count_tokens(text) > 0

    # tiktoken 에러 시 fallback 테스트
    with patch("tiktoken.encoding_for_model", side_effect=Exception("Error")):
        assert count_tokens("1234") == 1  # 4 chars // 4 = 1


def test_read_file_content():
    """read_file_content 함수 테스트"""
    mock_content = "File Content"
    with patch("builtins.open", mock_open(read_data=mock_content)):
        assert read_file_content("test.txt") == mock_content

    # 에러 처리 테스트 (OSError → RuntimeError 래핑 검증)
    with patch("builtins.open", side_effect=OSError("File not found")):
        with pytest.raises(RuntimeError, match="파일 읽기 실패") as excinfo:
            read_file_content("test.txt")
        assert "File not found" in str(excinfo.value)


def test_format_file_size():
    """format_file_size 함수 테스트"""
    assert format_file_size(500) == "500.0 B"
    assert format_file_size(1024) == "1.0 KB"
    assert format_file_size(1024 * 1024) == "1.0 MB"
    assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"
    assert format_file_size(1024 * 1024 * 1024 * 1024) == "1.0 TB"


def test_estimate_cost():
    """estimate_cost 함수 테스트"""
    assert estimate_cost(1000, 0.001) == 1.0


def test_load_pdf():
    """load_pdf 함수 테스트"""
    mock_file = MagicMock()
    mock_pdf_reader = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "PDF Page Content"
    mock_pdf_reader.pages = [mock_page]

    with patch("pypdf.PdfReader", return_value=mock_pdf_reader):
        text = load_pdf(mock_file)
        assert "PDF Page Content" in text

    # 에러 처리 테스트 (ValueError → RuntimeError 래핑 검증)
    with patch("pypdf.PdfReader", side_effect=ValueError("PDF Error")):
        with pytest.raises(RuntimeError, match="PDF 읽기 실패") as excinfo:
            load_pdf(mock_file)
        assert "PDF Error" in str(excinfo.value)


def test_save_to_markdown(tmp_path):
    """save_to_markdown 함수 테스트"""
    file_path = tmp_path / "test.md"
    save_to_markdown("Content", str(file_path), "Title")

    assert file_path.exists()
    content = file_path.read_text(encoding="utf-8")
    assert "# Title" in content
    assert "Content" in content

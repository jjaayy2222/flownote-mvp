# tests/unit/test_diff_service.py

import pytest
from backend.services.diff_service import generate_diff


def test_generate_diff_partial_change():
    """일부분만 변경된 경우 테스트"""
    local = "Hello\nWorld\nPython"
    remote = "Hello\nWorld\nRust"  # Python -> Rust 변경

    result = generate_diff(local, remote)

    assert "unified" in result
    assert "html" in result
    assert "stats" in result

    # 통계 검증: -Python (1 line), +Rust (1 line)
    assert result["stats"]["deletions"] == 1
    assert result["stats"]["additions"] == 1

    # Unified Diff 내용 검증
    assert "-Python" in result["unified"]
    assert "+Rust" in result["unified"]


def test_generate_diff_identical():
    """내용이 동일한 경우 테스트"""
    content = "Line 1\nLine 2"
    result = generate_diff(content, content)

    # 변경사항이 없어야 함
    assert result["stats"]["additions"] == 0
    assert result["stats"]["deletions"] == 0
    assert result["unified"] == ""  # 변경 없으면 빈 문자열


def test_generate_diff_empty_files():
    """파일이 비어있는 경우 테스트"""
    local = ""
    remote = "New Content"

    result = generate_diff(local, remote)

    assert result["stats"]["additions"] > 0
    assert result["stats"]["deletions"] == 0
    assert "+New Content" in result["unified"]


def test_generate_diff_multi_line_changes():
    """여러 줄 변경 및 삽입 테스트"""
    local = """func main() {
    print("Hello")
}"""
    remote = """func main() {
    # Changed comment
    print("Hello World")
    return 0
}"""

    result = generate_diff(local, remote)

    stats = result["stats"]
    assert stats["additions"] > 0
    assert stats["deletions"] > 0

    # HTML Diff 생성 여부 확인
    assert "<table" in result["html"]

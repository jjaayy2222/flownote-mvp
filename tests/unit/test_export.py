# tests/unit/test_export.py

"""
[KO] backend/export.py MarkdownExporter에 대한 단위 테스트.
[EN] Unit tests for MarkdownExporter in backend/export.py.
"""

import re
from typing import List

from backend.export import MarkdownExporter, SearchResult


class TestMarkdownExporter:
    """MarkdownExporter.export_search_results 메서드를 검증합니다."""

    def setup_method(self):
        self.exporter = MarkdownExporter()

    # --- 기본 헤더 출력 ---

    def test_header_contains_query(self):
        result = self.exporter.export_search_results("테스트 쿼리", [])
        assert "테스트 쿼리" in result

    def test_header_contains_result_count_zero(self):
        result = self.exporter.export_search_results("empty", [])
        assert "0개" in result

    def test_header_contains_result_count_multiple(self):
        results: List[SearchResult] = [
            {"content": "a", "score": 0.9, "metadata": {}},
            {"content": "b", "score": 0.8, "metadata": {}},
        ]
        result = self.exporter.export_search_results("multi", results)
        assert "2개" in result

    def test_header_contains_timestamp_format(self):
        """타임스탬프가 'YYYY-MM-DD HH:MM:SS' 형식을 포함하는지 확인합니다."""
        result = self.exporter.export_search_results("q", [])
        assert re.search(
            r"- \*\*검색 시간\*\*: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", result
        )

    # --- 결과 본문 렌더링 ---

    def test_single_result_content_rendered(self):
        results: List[SearchResult] = [{"content": "안녕하세요", "score": 0.95}]
        result = self.exporter.export_search_results("hello", results)
        assert "안녕하세요" in result

    def test_score_rendered_as_percentage(self):
        results: List[SearchResult] = [{"content": "text", "score": 0.75}]
        result = self.exporter.export_search_results("q", results)
        assert "75.00%" in result

    def test_multiple_results_indexed(self):
        results: List[SearchResult] = [
            {"content": "first", "score": 0.9},
            {"content": "second", "score": 0.7},
        ]
        result = self.exporter.export_search_results("q", results)
        assert "1번째 결과" in result
        assert "2번째 결과" in result

    # --- 메타데이터 포함/제외 ---

    def test_metadata_included_by_default(self):
        results: List[SearchResult] = [
            {
                "content": "data",
                "score": 0.8,
                "metadata": {"source": "note.md", "chunk_index": 3, "file_size": 1024},
            }
        ]
        result = self.exporter.export_search_results("q", results)
        assert "- **출처**: note.md" in result
        assert "- **청크 번호**: 3" in result
        assert "- **파일 크기**: 1024 bytes" in result

    def test_metadata_reads_streamlit_filename_and_file_type(self):
        """Streamlit 업로드/검색 경로에서 filename과 file_type 메타데이터를 올바르게 읽어야 합니다."""
        results: List[SearchResult] = [
            {
                "content": "streamlit data",
                "score": 0.9,
                "metadata": {"filename": "document.pdf", "file_type": "pdf"},
            }
        ]
        result = self.exporter.export_search_results("q", results)
        assert "- **출처**: document.pdf" in result
        assert "- **파일 유형**: pdf" in result
        assert "출처: N/A" not in result

    def test_metadata_excluded_when_flag_false(self):
        results: List[SearchResult] = [
            {
                "content": "data",
                "score": 0.8,
                "metadata": {
                    "source": "secret.md",
                    "chunk_index": 1,
                    "file_size": 2048,
                },
            }
        ]
        result = self.exporter.export_search_results(
            "q", results, include_metadata=False
        )
        assert "secret.md" not in result
        assert "### 메타데이터" not in result
        assert "출처" not in result
        assert "청크 번호" not in result
        assert "- **청크 번호**: 1" not in result
        assert "2048" not in result
        assert "파일 크기" not in result

    def test_empty_metadata_dict_skips_metadata_block(self):
        """메타데이터가 빈 딕셔너리이면 메타데이터 섹션 헤더와 내용이 일절 렌더링되지 않아야 합니다."""
        results: List[SearchResult] = [
            {"content": "data", "score": 0.5, "metadata": {}}
        ]
        result = self.exporter.export_search_results("q", results)
        assert "### 메타데이터" not in result
        assert "출처" not in result
        assert "청크 번호" not in result
        assert "파일 크기" not in result

    def test_missing_metadata_key_falls_back_to_na(self):
        """메타데이터에 일부 키가 없으면 각각 독립적으로 N/A로 표시되어야 합니다."""
        results: List[SearchResult] = [
            {"content": "data", "score": 0.5, "metadata": {"source": "file.md"}}
        ]
        result = self.exporter.export_search_results("q", results)
        assert "- **출처**: file.md" in result
        assert "- **청크 번호**: N/A" in result
        assert "- **파일 크기**: N/A bytes" in result

    # --- 엣지 케이스 ---

    def test_empty_results_returns_header_only(self):
        result = self.exporter.export_search_results("q", [])
        assert "FlowNote 검색 결과" in result
        assert "1번째 결과" not in result

    def test_missing_content_key_defaults_to_empty_string(self):
        results: List[SearchResult] = [{"score": 0.5}]
        result = self.exporter.export_search_results("q", results)
        assert "1번째 결과" in result
        # content 키가 없을 때 정확히 빈 문자열 내용 블록("### 내용\n\n\n\n")이 렌더링되어야 합니다
        assert "### 내용\n\n\n\n" in result

    def test_missing_score_key_defaults_to_zero(self):
        results: List[SearchResult] = [{"content": "text"}]
        result = self.exporter.export_search_results("q", results)
        assert "0.00%" in result

    def test_returns_string(self):
        result = self.exporter.export_search_results("q", [])
        assert isinstance(result, str)

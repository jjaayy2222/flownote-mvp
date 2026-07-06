# backend/export.py

"""
FlowNote MVP - Markdown Exporter Module (마크다운 내보내기).

[KO] RAG 검색 결과나 노트 데이터를 마크다운(Markdown) 포맷 등 외부 파일 형식으로 내보내는 유틸리티 모듈입니다.
[EN] Utility module for exporting RAG search results or note data into external file formats like Markdown.
"""

from datetime import datetime
from typing import Any, Dict, List


class MarkdownExporter:
    """
    [KO] 검색 결과를 마크다운(Markdown) 문자열로 변환하는 클래스.
    [EN] Class to convert search results into Markdown formatted strings.
    """

    def __init__(self):
        pass

    def export_search_results(
        self, query: str, results: List[Dict[str, Any]], include_metadata: bool = True
    ) -> str:
        """
        [KO] 검색 결과 리스트를 마크다운 형식의 문자열로 변환합니다.
        [EN] Converts a list of search results into a Markdown formatted string.

        Args:
            query: [KO] 사용자가 입력한 원본 검색 쿼리. [EN] The original search query entered by the user.
            results: [KO] 검색 엔진으로부터 반환된 결과 딕셔너리 리스트. [EN] List of result dictionaries returned from the search engine.
            include_metadata: [KO] 문서 출처, 청크 번호 등 메타데이터 포함 여부 (기본값 True). [EN] Whether to include metadata such as source and chunk index (default True).

        Returns:
            [KO] 포맷팅이 완료된 마크다운 문자열.
            [EN] The fully formatted Markdown string.
        """

        # 시간
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 헤더
        md = f"# FlowNote 검색 결과\n\n"
        md += f"- **검색어**: {query}\n"
        md += f"- **검색 시간**: {timestamp}\n"
        md += f"- **결과 수**: {len(results)}개\n\n"
        md += "---\n\n"

        # 결과
        for i, result in enumerate(results, 1):
            md += f"## {i}번째 결과\n\n"

            # 유사도
            score = result.get("score", 0)
            md += f"**유사도**: {score:.2%}\n\n"

            # 내용
            content = result.get("content", "")
            md += f"### 내용\n\n{content}\n\n"

            # 메타데이터
            if include_metadata:
                if metadata := result.get("metadata", {}):
                    md += f"### 메타데이터\n\n"
                    md += f"- **출처**: {metadata.get('source', 'N/A')}\n"
                    md += f"- **청크 번호**: {metadata.get('chunk_index', 'N/A')}\n"
                    md += f"- **파일 크기**: {metadata.get('file_size', 'N/A')} bytes\n"
                    md += "\n"

            md += "---\n\n"

        return md

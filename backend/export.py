# backend/export.py

"""
FlowNote MVP - 마크다운 내보내기
"""

from datetime import datetime
from typing import List, Dict

class MarkdownExporter:
    """검색 결과를 마크다운으로 변환"""
    
    def __init__(self):
        pass
    
    def export_search_results(
        self,
        query: str,
        results: List[Dict],
        include_metadata: bool = True
    ) -> str:
        """
        검색 결과를 마크다운 형식으로 변환
        
        Args:
            query: 검색 쿼리
            results: 검색 결과 리스트
            include_metadata: 메타데이터 포함 여부
            
        Returns:
            마크다운 문자열
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
            score = result.get('score', 0)
            md += f"**유사도**: {score:.2%}\n\n"
            
            # 내용
            content = result.get('content', '')
            md += f"### 내용\n\n{content}\n\n"
            
            # 메타데이터
            if include_metadata:
                metadata = result.get('metadata', {})
                if metadata:
                    md += f"### 메타데이터\n\n"
                    md += f"- **출처**: {metadata.get('source', 'N/A')}\n"
                    md += f"- **청크 번호**: {metadata.get('chunk_index', 'N/A')}\n"
                    md += f"- **파일 크기**: {metadata.get('file_size', 'N/A')} bytes\n"
                    md += "\n"
            
            md += "---\n\n"
        
        return md
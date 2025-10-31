# backend/dashboard/dashboard_core.py

from backend.database.connection import DatabaseConnection
from typing import Dict, Any, List

class MetadataAggregator:
    """메타데이터 수집 및 집계"""
    
    def __init__(self):
        self.db = DatabaseConnection()
    
    def get_file_statistics(self) -> Dict[str, Any]:
        """파일 통계 수집"""
        return {
            'total_files': len(self.db.get_all_files()),
            'total_searches': self.db.get_total_searches(),
            'by_type': self.db._group_by_extension(),
            'by_category': self.db._group_by_para(),
            'top_keywords': self.db.get_top_keywords(top_n=10)
        }
    
    def get_para_breakdown(self) -> Dict[str, int]:
        """PARA별 파일 수"""
        return {
            'Projects': self.db.count_by_para('projects'),
            'Areas': self.db.count_by_para('areas'),
            'Resources': self.db.count_by_para('resources'),
            'Archive': self.db.count_by_para('archive')
        }
    
    def get_keyword_categories(self) -> Dict[str, int]:
        """키워드 기반 카테고리화"""
        return {
            '업무': self.db.count_by_keyword_tag('업무'),
            '개인': self.db.count_by_keyword_tag('개인'),
            '학습': self.db.count_by_keyword_tag('학습'),
            '참고자료': self.db.count_by_keyword_tag('참고자료')
        }
    
    def get_top_keywords(self, top_n: int = 10) -> List[str]:
        """상위 키워드"""
        return self.db.get_top_keywords(top_n)

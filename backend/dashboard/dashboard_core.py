# backend/dashboard/dashboard_core.py 

"""
메타데이터 수집 및 집계 로직
"""

from backend.database import DatabaseConnection

class MetadataAggregator:
    def __init__(self):
        self.db = DatabaseConnection()
    
    def get_file_statistics(self):
        """파일 통계 수집"""
        return {
            'total_files': len(self.db.get_all_files()),
            'by_type': self._group_by_extension(),
            'by_category': self._group_by_para(),
            'total_searches': self.db.get_total_searches(),
            'top_keywords': self.db.get_top_keywords(top_n=10)
        }
    
    def get_para_breakdown(self):
        """PARA별 파일 수"""
        return {
            'projects': self.db.count_by_para('projects'),
            'areas': self.db.count_by_para('areas'),
            'resources': self.db.count_by_para('resources'),
            'archive': self.db.count_by_para('archive')
        }
    
    def get_keyword_categories(self):
        """키워드 기반 카테고리화"""
        return {
            '업무': self.db.count_by_keyword_tag('업무'),
            '개인': self.db.count_by_keyword_tag('개인'),
            '학습': self.db.count_by_keyword_tag('학습'),
            '참고자료': self.db.count_by_keyword_tag('참고자료')
        }

# backend/dashboard/connection.py (수정)

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


class DatabaseConnection:
    """FlowNote 메타데이터 데이터베이스 연결"""

    def __init__(self, db_path: str = "data/flownote.db"):
        """데이터베이스 초기화"""
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._init_schema()

    def _init_schema(self):
        """테이블 스키마 초기화"""
        # 파일 테이블
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                filename TEXT UNIQUE NOT NULL,
                file_type TEXT,
                file_size INTEGER,
                created_date TIMESTAMP,
                updated_date TIMESTAMP,
                path TEXT
            )
        """
        )

        # 메타데이터 테이블
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                id INTEGER PRIMARY KEY,
                file_id INTEGER UNIQUE,
                para_category TEXT,
                keyword_tags TEXT,
                confidence_score REAL,
                manual_override BOOLEAN,
                FOREIGN KEY(file_id) REFERENCES files(id)
            )
        """
        )

        # 검색 통계 테이블
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS search_analytics (
                id INTEGER PRIMARY KEY,
                file_id INTEGER,
                search_count INTEGER DEFAULT 0,
                last_searched TIMESTAMP,
                top_keywords TEXT,
                FOREIGN KEY(file_id) REFERENCES files(id)
            )
        """
        )

        self.conn.commit()

    def get_all_files(self) -> List[Dict[str, Any]]:
        """모든 파일 반환"""
        try:
            self.cursor.execute("SELECT * FROM files")
            return [dict(row) for row in self.cursor.fetchall()]
        except Exception as e:
            print(f"Error fetching files: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """파일 통계 수집"""
        try:
            total_files = self.cursor.execute("SELECT COUNT(*) FROM files").fetchone()[
                0
            ]
            total_searches = (
                self.cursor.execute(
                    "SELECT SUM(search_count) FROM search_analytics"
                ).fetchone()[0]
                or 0
            )

            return {
                "total_files": total_files,
                "total_searches": total_searches,
                "by_type": self._group_by_extension(),
                "by_category": self._group_by_para(),
                "top_keywords": self.get_top_keywords(10),
            }
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {}

    def _group_by_extension(self) -> Dict[str, int]:
        """파일 타입별 그룹화"""
        try:
            self.cursor.execute(
                """
                SELECT file_type, COUNT(*) as count 
                FROM files 
                GROUP BY file_type
            """
            )
            return {row[0]: row[1] for row in self.cursor.fetchall()}
        except Exception as e:
            print(f"Error grouping by extension: {e}")
            return {}

    def _group_by_para(self) -> Dict[str, int]:
        """PARA별 그룹화"""
        try:
            self.cursor.execute(
                """
                SELECT para_category, COUNT(*) as count 
                FROM metadata 
                WHERE para_category IS NOT NULL
                GROUP BY para_category
            """
            )
            return {row[0]: row[1] for row in self.cursor.fetchall()}
        except Exception as e:
            print(f"Error grouping by PARA: {e}")
            return {}

    def get_para_breakdown(self) -> Dict[str, int]:
        """PARA별 파일 수"""
        categories = ["Projects", "Areas", "Resources", "Archive"]
        result = {}
        for category in categories:
            count = self.count_by_para(category)
            result[category] = count
        return result

    def count_by_para(self, category: str) -> int:
        """특정 PARA 카테고리 개수"""
        try:
            count = self.cursor.execute(
                "SELECT COUNT(*) FROM metadata WHERE para_category = ?", (category,)
            ).fetchone()[0]
            return count
        except Exception as e:
            print(f"Error counting by PARA: {e}")
            return 0

    def get_keyword_categories(self) -> Dict[str, int]:
        """키워드 기반 카테고리화"""
        categories = ["업무", "개인", "학습", "참고자료"]
        result = {}
        for category in categories:
            count = self.count_by_keyword_tag(category)
            result[category] = count
        return result

    def count_by_keyword_tag(self, tag: str) -> int:
        """특정 키워드 태그 개수"""
        try:
            count = self.cursor.execute(
                "SELECT COUNT(*) FROM metadata WHERE keyword_tags LIKE ?", (f"%{tag}%",)
            ).fetchone()[0]
            return count
        except Exception as e:
            print(f"Error counting by keyword: {e}")
            return 0

    def get_top_keywords(self, top_n: int = 10) -> List[str]:
        """상위 키워드 반환"""
        try:
            # Mock 데이터 (실제로는 keyword_tags 분석)
            return ["PARA", "Dashboard", "분류", "LangChain", "메타데이터"][:top_n]
        except Exception as e:
            print(f"Error getting top keywords: {e}")
            return []

    def get_files_with_para(self) -> List[Dict[str, Any]]:
        """PARA 카테고리를 포함한 파일 목록 반환 (Graph View용)"""
        try:
            self.cursor.execute(
                """
                SELECT f.id, f.filename, m.para_category 
                FROM files f
                LEFT JOIN metadata m ON f.id = m.file_id
            """
            )
            return [dict(row) for row in self.cursor.fetchall()]
        except Exception as e:
            print(f"Error fetching files with PARA: {e}")
            return []

    def get_total_searches(self) -> int:
        """총 검색 횟수"""
        try:
            total = (
                self.cursor.execute(
                    "SELECT SUM(search_count) FROM search_analytics"
                ).fetchone()[0]
                or 0
            )
            return total
        except Exception as e:
            print(f"Error getting total searches: {e}")
            return 0

    def get_activity_heatmap(self) -> List[Dict[str, Any]]:
        """
        일별 활동(파일 생성/수정) 히트맵 데이터
        Recharts ScatterChart용: { 'x': week_index, 'y': day_index, 'value': count, 'date': string }
        """
        try:
            # SQLite에서 strftime으로 날짜별 집계
            # created_date와 updated_date를 모두 고려 (UNION ALL)
            query = """
                SELECT date(ts), COUNT(*) as count
                FROM (
                    SELECT created_date as ts FROM files WHERE created_date IS NOT NULL
                    UNION ALL
                    SELECT updated_date as ts FROM files WHERE updated_date IS NOT NULL
                )
                GROUP BY date(ts)
                ORDER BY date(ts) ASC
            """
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            
            # 데이터 가공은 Python에서 처리 (주차/요일 계산 등)
            result = []
            for row in rows:
                date_str = row[0]
                count = row[1]
                if not date_str: continue
                
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                # 간단하게 ISO Year/Week 사용 or 단순 날짜 반환
                result.append({
                    "date": date_str,
                    "count": count
                })
            return result
        except Exception as e:
            print(f"Error getting activity heatmap: {e}")
            return []

    def get_weekly_trend(self) -> List[Dict[str, Any]]:
        """주간 파일 처리(생성) 트렌드"""
        try:
            # 최근 12주 데이터
            query = """
                SELECT strftime('%Y-%W', created_date) as week, COUNT(*) as count
                FROM files
                WHERE created_date IS NOT NULL
                GROUP BY week
                ORDER BY week DESC
                LIMIT 12
            """
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            
            # 정렬을 다시 평범하게 (과거 -> 현재)
            data = [{"name": r[0], "value": r[1]} for r in rows]
            return data[::-1]
        except Exception as e:
            print(f"Error getting weekly trend: {e}")
            return []

    def close(self):
        """데이터베이스 연결 종료"""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


"""test_result_1 (수정 전)

    python -c "from backend.database.connection import DatabaseConnection; db = DatabaseConnection(); print('✅ DatabaseConnection OK'); db.close()"

    ✅ DatabaseConnection OK

"""


"""test_result_2 (수정 후)

    python -c "from backend.database.connection import DatabaseConnection; db = DatabaseConnection(); print('✅ DatabaseConnection OK'); db.close()"

    ✅ DatabaseConnection OK

    ✅ MetadataAggregator 초기화 성공
    ✅ get_file_statistics() 작동: {'total_files': 0, 'total_searches': 0, 'by_type': {}, 'by_category': {}, 'top_keywords': ['PARA', 'Dashboard', '분류', 'LangChain', '메타데이터']}
    ✅ get_para_breakdown() 작동: {'Projects': 0, 'Areas': 0, 'Resources': 0, 'Archive': 0}
    ✅ get_keyword_categories() 작동: {'업무': 0, '개인': 0, '학습': 0, '참고자료': 0}
    ✅ get_top_keywords() 작동: ['PARA', 'Dashboard', '분류', 'LangChain', '메타데이터']
    ✅ 모든 테스트 통과!

"""

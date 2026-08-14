# backend/database/connection.py
"""
[KO] FlowNote 메타데이터 SQLite 데이터베이스 연결 및 쿼리 헬퍼 모듈.

설계 원칙:
  - 모든 DB 예외는 sqlite3 전용 구체 타입(OperationalError, DatabaseError 등)으로 처리합니다.
  - 에러 메시지에 PII(경로, 파일명 원문 등)를 로그에 직접 남기지 않습니다.
  - 순환 의존성 방지를 위해 agent 계층을 import하지 않으며,
    표준 logging을 통해 구조화된 포맷으로 에러를 기록합니다.

[EN] FlowNote metadata SQLite database connection and query helper module.

Design Principles:
  - All DB exceptions are handled with sqlite3-specific concrete types.
  - PII (raw paths, filenames, etc.) is never written directly to logs.
  - Does NOT import agent-layer modules to prevent circular dependencies.
    Errors are recorded via standard logging in structured format.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    [KO] FlowNote 메타데이터 데이터베이스 연결 클래스.
    [EN] FlowNote metadata database connection class.
    """

    def __init__(self, db_path: str = "data/flownote.db"):
        """
        [KO] 데이터베이스 초기화. 디렉터리가 없으면 자동 생성합니다.
        [EN] Initializes the database. Creates parent directories if missing.
        """
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._init_schema()

    def _init_schema(self) -> None:
        """
        [KO] 테이블 스키마 초기화. 이미 존재하는 테이블은 건드리지 않습니다.
        [EN] Initializes table schema. Skips creation if tables already exist.
        """
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
        """
        [KO] 모든 파일 레코드를 반환합니다.
        [EN] Returns all file records.
        """
        try:
            self.cursor.execute("SELECT * FROM files")
            return [dict(row) for row in self.cursor.fetchall()]
        except sqlite3.OperationalError:
            logger.error(
                "[DB] get_all_files: 쿼리 실행 실패 / Query execution failed",
                exc_info=True,
                extra={"action": "get_all_files", "table": "files"},
            )
            return []
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] get_all_files: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "get_all_files", "table": "files"},
            )
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """
        [KO] 파일 통계를 수집하여 반환합니다.
        [EN] Collects and returns file statistics.
        """
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
        except sqlite3.OperationalError:
            logger.error(
                "[DB] get_statistics: 통계 쿼리 실패 / Statistics query failed",
                exc_info=True,
                extra={"action": "get_statistics"},
            )
            return {}
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] get_statistics: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "get_statistics"},
            )
            return {}

    def _group_by_extension(self) -> Dict[str, int]:
        """
        [KO] 파일 타입별로 그룹화하여 반환합니다.
        [EN] Groups and returns file counts by file type.
        """
        try:
            self.cursor.execute(
                """
                SELECT file_type, COUNT(*) as count
                FROM files
                GROUP BY file_type
            """
            )
            return {row[0]: row[1] for row in self.cursor.fetchall()}
        except sqlite3.OperationalError:
            logger.error(
                "[DB] _group_by_extension: 그룹화 쿼리 실패 / Group-by-extension query failed",
                exc_info=True,
                extra={"action": "_group_by_extension", "table": "files"},
            )
            return {}
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] _group_by_extension: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "_group_by_extension"},
            )
            return {}

    def _group_by_para(self) -> Dict[str, int]:
        """
        [KO] PARA 카테고리별로 그룹화하여 반환합니다.
        [EN] Groups and returns file counts by PARA category.
        """
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
        except sqlite3.OperationalError:
            logger.error(
                "[DB] _group_by_para: PARA 그룹화 쿼리 실패 / Group-by-PARA query failed",
                exc_info=True,
                extra={"action": "_group_by_para", "table": "metadata"},
            )
            return {}
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] _group_by_para: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "_group_by_para"},
            )
            return {}

    def get_para_breakdown(self) -> Dict[str, int]:
        """
        [KO] PARA 카테고리별 파일 수를 반환합니다.
        [EN] Returns file counts per PARA category.
        """
        categories = ["Projects", "Areas", "Resources", "Archive"]
        return {category: self.count_by_para(category) for category in categories}

    def count_by_para(self, category: str) -> int:
        """
        [KO] 특정 PARA 카테고리의 파일 수를 반환합니다.
        [EN] Returns file count for a specific PARA category.
        """
        try:
            return self.cursor.execute(
                "SELECT COUNT(*) FROM metadata WHERE para_category = ?", (category,)
            ).fetchone()[0]
        except sqlite3.OperationalError:
            logger.error(
                "[DB] count_by_para: 카테고리 카운트 쿼리 실패 / Count-by-PARA query failed",
                exc_info=True,
                extra={"action": "count_by_para", "table": "metadata"},
            )
            return 0
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] count_by_para: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "count_by_para"},
            )
            return 0

    def get_keyword_categories(self) -> Dict[str, int]:
        """
        [KO] 키워드 태그 기반 카테고리별 파일 수를 반환합니다.
        [EN] Returns file counts per keyword-tag-based category.
        """
        categories = ["업무", "개인", "학습", "참고자료"]
        return {
            category: self.count_by_keyword_tag(category) for category in categories
        }

    def count_by_keyword_tag(self, tag: str) -> int:
        """
        [KO] 특정 키워드 태그를 포함하는 파일 수를 반환합니다.
        [EN] Returns count of files containing the specified keyword tag.
        """
        try:
            return self.cursor.execute(
                "SELECT COUNT(*) FROM metadata WHERE keyword_tags LIKE ?",
                (f"%{tag}%",),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            logger.error(
                "[DB] count_by_keyword_tag: 키워드 카운트 쿼리 실패 / Count-by-keyword query failed",
                exc_info=True,
                extra={"action": "count_by_keyword_tag", "table": "metadata"},
            )
            return 0
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] count_by_keyword_tag: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "count_by_keyword_tag"},
            )
            return 0

    def get_top_keywords(self, top_n: int = 10) -> List[str]:
        """
        [KO] 상위 키워드 목록을 반환합니다 (현재 Mock 데이터).
        [EN] Returns top keyword list (currently mock data).
        """
        # Mock 데이터 — 실제 keyword_tags 분석 로직으로 대체 예정
        mock_keywords = ["PARA", "Dashboard", "분류", "LangChain", "메타데이터"]
        return mock_keywords[:top_n]

    def get_files_with_para(self) -> List[Dict[str, Any]]:
        """
        [KO] PARA 카테고리를 포함한 파일 목록을 반환합니다 (Graph View용).
        [EN] Returns file list with PARA categories (for Graph View).
        """
        try:
            self.cursor.execute(
                """
                SELECT f.id, f.filename, m.para_category
                FROM files f
                LEFT JOIN metadata m ON f.id = m.file_id
            """
            )
            return [dict(row) for row in self.cursor.fetchall()]
        except sqlite3.OperationalError:
            logger.error(
                "[DB] get_files_with_para: JOIN 쿼리 실패 / Files-with-PARA query failed",
                exc_info=True,
                extra={"action": "get_files_with_para", "tables": "files,metadata"},
            )
            return []
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] get_files_with_para: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "get_files_with_para"},
            )
            return []

    def get_total_searches(self) -> int:
        """
        [KO] 총 검색 횟수를 반환합니다.
        [EN] Returns total search count.
        """
        try:
            return (
                self.cursor.execute(
                    "SELECT SUM(search_count) FROM search_analytics"
                ).fetchone()[0]
                or 0
            )
        except sqlite3.OperationalError:
            logger.error(
                "[DB] get_total_searches: 검색 합계 쿼리 실패 / Total-searches query failed",
                exc_info=True,
                extra={"action": "get_total_searches", "table": "search_analytics"},
            )
            return 0
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] get_total_searches: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "get_total_searches"},
            )
            return 0

    def get_activity_heatmap(self) -> List[Dict[str, Any]]:
        """
        [KO] 일별 활동(파일 생성/수정) 히트맵 데이터를 반환합니다.
        Recharts ScatterChart용 포맷: { 'date': str, 'count': int }

        [EN] Returns daily activity (file create/update) heatmap data.
        Format for Recharts ScatterChart: { 'date': str, 'count': int }
        """
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
        try:
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
        except sqlite3.OperationalError:
            logger.error(
                "[DB] get_activity_heatmap: 히트맵 쿼리 실패 / Activity-heatmap query failed",
                exc_info=True,
                extra={"action": "get_activity_heatmap"},
            )
            return []
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] get_activity_heatmap: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "get_activity_heatmap"},
            )
            return []

        result = []
        for row in rows:
            date_str = row[0]
            count = row[1]
            if not date_str:
                continue
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                # 날짜 형식이 잘못된 행은 조용히 건너뜁니다 (PII 노출 없이)
                logger.warning(
                    "[DB] get_activity_heatmap: 날짜 파싱 실패, 해당 행 건너뜀 / Invalid date format, skipping row",
                    extra={"action": "get_activity_heatmap"},
                )
                continue
            result.append({"date": date_str, "count": count})
        return result

    def get_weekly_trend(self) -> List[Dict[str, Any]]:
        """
        [KO] 최근 12주간 파일 처리(생성) 트렌드를 반환합니다.
        [EN] Returns file creation trend for the past 12 weeks.
        """
        query = """
            SELECT strftime('%Y-%W', created_date) as week, COUNT(*) as count
            FROM files
            WHERE created_date IS NOT NULL
            GROUP BY week
            ORDER BY week DESC
            LIMIT 12
        """
        try:
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            data = [{"name": r[0], "value": r[1]} for r in rows]
            return data[::-1]  # 과거 → 현재 순으로 정렬
        except sqlite3.OperationalError:
            logger.error(
                "[DB] get_weekly_trend: 주간 트렌드 쿼리 실패 / Weekly-trend query failed",
                exc_info=True,
                extra={"action": "get_weekly_trend", "table": "files"},
            )
            return []
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] get_weekly_trend: DB 오류 / Database error",
                exc_info=True,
                extra={"action": "get_weekly_trend"},
            )
            return []

    def close(self) -> None:
        """
        [KO] 데이터베이스 연결을 종료합니다.
        [EN] Closes the database connection.
        """
        if self.conn:
            self.conn.close()

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
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

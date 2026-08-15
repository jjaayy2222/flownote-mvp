# backend/database/connection.py
"""
[KO] FlowNote 메타데이터 SQLite 데이터베이스 연결 및 쿼리 헬퍼 모듈.

설계 원칙:
  - 모든 DB 예외는 sqlite3 전용 구체 타입(OperationalError, DatabaseError 등)으로 처리합니다.
  - 에러 메시지에 PII(경로, 파일명 원문 등)를 로그에 직접 남기지 않습니다.
  - 순환 의존성 방지를 위해 agent 계층을 import하지 않으며,
    표준 logging을 통해 구조화된 포맷으로 에러를 기록합니다.
  - _execute_query 내부 헬퍼로 반복되는 try/except 패턴을 단일 지점에서 관리합니다.

[EN] FlowNote metadata SQLite database connection and query helper module.

Design Principles:
  - All DB exceptions are handled with sqlite3-specific concrete types.
  - PII (raw paths, filenames, etc.) is never written directly to logs.
  - Does NOT import agent-layer modules to prevent circular dependencies.
    Errors are recorded via standard logging in structured format.
  - _execute_query helper centralizes repeated try/except patterns in one place.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

# fetch 옵션 타입 — 정적 분석 및 자동완성 지원
_FetchMode = Literal["all", "one", "none"]

# default 파라미터의 '미지정' 여부를 구분하는 센티넬
# (None을 유효한 기본값으로 허용하기 위해 별도 객체 사용)
_MISSING: object = object()


class DatabaseConnection:
    """
    [KO] FlowNote 메타데이터 데이터베이스 연결 클래스.
    [EN] FlowNote metadata database connection class.
    """

    def __init__(self, db_path: str = "data/flownote.db"):
        """
        [KO] 데이터베이스 초기화. 디렉터리가 없으면 자동 생성합니다.
        [EN] Initializes the database. Creates parent directories if missing.

        Note:
            row_factory를 sqlite3.Row로 설정하여 fetchall() 결과에서
            dict(row) 변환이 안전하게 작동하도록 합니다.
            / Sets row_factory to sqlite3.Row so dict(row) conversion
            works correctly on fetchall() results.
        """
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._init_schema()

    # ─────────────────────────────────────────────────────────────────────────
    # 내부 헬퍼 (Internal Helpers)
    # ─────────────────────────────────────────────────────────────────────────

    def _execute_query(
        self,
        query: str,
        params: Tuple[Any, ...] = (),
        *,
        action: str,
        table: Optional[str] = None,
        fetch: _FetchMode = "all",
        default: Any = _MISSING,
    ) -> Any:
        """
        [KO] 쿼리 실행과 에러 처리를 중앙집중화하는 내부 헬퍼입니다.
        반복되는 sqlite3 예외 처리 및 구조화 로깅 패턴을 단일 지점으로 통합합니다.
        쿼리 파라미터(params)는 PII 보호를 위해 로그에 절대 기록하지 않습니다.

        [EN] Internal helper that centralizes query execution and error handling.
        Consolidates repeated sqlite3 exception handling and structured logging.
        Query params are never logged to protect PII.

        Args:
            query:   실행할 SQL 쿼리 / SQL query to execute.
            params:  쿼리 파라미터 (로그 미포함) / Query parameters (never logged).
            action:  로그 컨텍스트용 메서드명 / Method name for log context.
            table:   관련 테이블명 (선택) / Related table name (optional).
            fetch:   결과 fetch 방식: "all" | "one" | "none"
            default: 예외 또는 빈 결과 시 반환할 기본값.
                     미지정 시 fetch 모드별로 자동 추론:
                       "all"  → [] (빈 리스트)
                       "one"  → None
                       "none" → None
                     / Fallback value on exception or empty result.
                     If omitted, inferred per fetch mode:
                       "all"  → [] (empty list)
                       "one"  → None
                       "none" → None
        """
        # fetch 모드별 합리적인 기본값 자동 추론
        if default is _MISSING:
            default = [] if fetch == "all" else None

        extra: Dict[str, Any] = {"action": action}
        if table:
            extra["table"] = table

        try:
            self.cursor.execute(query, params)
            if fetch == "all":
                return self.cursor.fetchall()
            if fetch == "one":
                result = self.cursor.fetchone()
                # fetchone()이 None을 반환할 때(빈 결과)도 default 반환
                # / Also return default when fetchone() returns None (no rows)
                return result if result is not None else default
            return None
        except sqlite3.OperationalError:
            logger.error(
                "[DB] %s: 쿼리 실행 실패 / Query execution failed",
                action,
                exc_info=True,
                extra=extra,
            )
            return default
        except sqlite3.DatabaseError:
            logger.error(
                "[DB] %s: DB 오류 / Database error",
                action,
                exc_info=True,
                extra=extra,
            )
            return default

    def _is_valid_date(self, date_str: str, action: str) -> bool:
        """
        [KO] 날짜 문자열이 'YYYY-MM-DD' 형식인지 검증합니다.
        유효하지 않으면 경고 로그를 남기고 False를 반환합니다.
        (PII 보호: 원본 날짜 문자열은 로그에 포함하지 않습니다.)

        [EN] Validates whether a date string matches the 'YYYY-MM-DD' format.
        Logs a warning and returns False if invalid.
        (PII safety: raw date string is never included in the log.)
        """
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            logger.warning(
                "[DB] %s: 날짜 파싱 실패, 해당 행 건너뜀 / Invalid date format, skipping row",
                action,
                extra={"action": action},
            )
            return False

    def _execute_scalar(
        self,
        query: str,
        params: Tuple[Any, ...] = (),
        *,
        action: str,
        table: Optional[str] = None,
        default: Any = 0,
    ) -> Any:
        """
        [KO] 단일 스칼라 값(예: COUNT, SUM, 단일 필드 조회)을 반환하는 쿼리의 전용 헬퍼입니다.
        _execute_query(fetch="one")를 래핑하여 튜플 인덱싱 없이 스칼라 값을 직접 반환합니다.
        SQL NULL(행 없을 때 SUM이 반환하는 값) 처리도 내부에서 일괄 처리합니다.

        [EN] Dedicated helper for queries returning a single scalar value (COUNT, SUM, etc.).
        Wraps _execute_query(fetch="one") to return the value directly without tuple indexing.
        Also handles SQL NULL (returned by SUM when no rows exist) internally.

        Args:
            query:   실행할 스칼라 SELECT 쿼리 / Scalar SELECT query to execute.
            params:  쿼리 파라미터 (로그 미포함) / Query parameters (never logged).
            action:  로그 컨텍스트용 메서드명 / Method name for log context.
            table:   관련 테이블명 (선택) / Related table name (optional).
            default: 예외 또는 NULL 결과 시 반환할 기본값 (기본값: 0)
                     / Fallback value for exceptions or SQL NULL results (default: 0).
        """
        row = self._execute_query(
            query,
            params,
            action=action,
            table=table,
            fetch="one",
            default=(default,),
        )
        # 방어적 코드: 반환된 결과가 시퀀스(튜플/리스트 등)이고 요소가 존재하는지 확인
        # / Defensive check: ensure the returned result is a sequence and has at least one element.
        if row and len(row) > 0:
            return row[0] if row[0] is not None else default
        return default

    # ─────────────────────────────────────────────────────────────────────────
    # 스키마 초기화 (Schema)
    # ─────────────────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────────────────
    # 공개 쿼리 메서드 (Public Query Methods)
    # ─────────────────────────────────────────────────────────────────────────

    def get_all_files(self) -> List[Dict[str, Any]]:
        """
        [KO] 모든 파일 레코드를 반환합니다.
        [EN] Returns all file records.
        """
        rows = self._execute_query(
            "SELECT * FROM files",
            action="get_all_files",
            table="files",
            fetch="all",
        )
        return [dict(row) for row in rows]

    def get_statistics(self) -> Dict[str, Any]:
        """
        [KO] 파일 통계를 수집하여 반환합니다.
        [EN] Collects and returns file statistics.
        """
        return {
            "total_files": self._execute_scalar(
                "SELECT COUNT(*) FROM files",
                action="get_statistics.total_files",
                table="files",
            ),
            "total_searches": self._execute_scalar(
                "SELECT SUM(search_count) FROM search_analytics",
                action="get_statistics.total_searches",
                table="search_analytics",
            ),
            "by_type": self._group_by_extension(),
            "by_category": self._group_by_para(),
            "top_keywords": self.get_top_keywords(10),
        }

    def _group_by_extension(self) -> Dict[str, int]:
        """
        [KO] 파일 타입별로 그룹화하여 반환합니다.
        [EN] Groups and returns file counts by file type.
        """
        rows = self._execute_query(
            """
            SELECT file_type, COUNT(*) as count
            FROM files
            GROUP BY file_type
            """,
            action="_group_by_extension",
            table="files",
            fetch="all",
        )
        return {row[0]: row[1] for row in rows}

    def _group_by_para(self) -> Dict[str, int]:
        """
        [KO] PARA 카테고리별로 그룹화하여 반환합니다.
        [EN] Groups and returns file counts by PARA category.
        """
        rows = self._execute_query(
            """
            SELECT para_category, COUNT(*) as count
            FROM metadata
            WHERE para_category IS NOT NULL
            GROUP BY para_category
            """,
            action="_group_by_para",
            table="metadata",
            fetch="all",
        )
        return {row[0]: row[1] for row in rows}

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
        return self._execute_scalar(
            "SELECT COUNT(*) FROM metadata WHERE para_category = ?",
            (category,),
            action="count_by_para",
            table="metadata",
        )

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
        return self._execute_scalar(
            "SELECT COUNT(*) FROM metadata WHERE keyword_tags LIKE ?",
            (f"%{tag}%",),
            action="count_by_keyword_tag",
            table="metadata",
        )

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
        rows = self._execute_query(
            """
            SELECT f.id, f.filename, m.para_category
            FROM files f
            LEFT JOIN metadata m ON f.id = m.file_id
            """,
            action="get_files_with_para",
            table="files,metadata",
            fetch="all",
        )
        return [dict(row) for row in rows]

    def get_total_searches(self) -> int:
        """
        [KO] 총 검색 횟수를 반환합니다.
        [EN] Returns total search count.
        """
        return self._execute_scalar(
            "SELECT SUM(search_count) FROM search_analytics",
            action="get_total_searches",
            table="search_analytics",
        )

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
        rows = self._execute_query(
            query,
            action="get_activity_heatmap",
            fetch="all",
        )

        result = []
        for row in rows:
            date_str, count = row[0], row[1]
            if not date_str or not self._is_valid_date(
                date_str, "get_activity_heatmap"
            ):
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
        rows = self._execute_query(
            query,
            action="get_weekly_trend",
            table="files",
            fetch="all",
        )
        # DB에서 최신순(DESC)으로 받은 결과를 과거→현재 순으로 뒤집어 반환
        # / Reverse DESC results from DB to return in chronological (ASC) order
        data = [{"name": r[0], "value": r[1]} for r in rows]
        return list(reversed(data))

    # ─────────────────────────────────────────────────────────────────────────
    # 연결 관리 (Connection Lifecycle)
    # ─────────────────────────────────────────────────────────────────────────

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

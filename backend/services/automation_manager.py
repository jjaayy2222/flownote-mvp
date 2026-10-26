# backend/services/automation_manager.py

"""
Automation Manager Service
자동화 로그, 규칙, 이력 관리를 위한 서비스 레이어
"""

import json
import logging
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.agent.error_utils import (  # type: ignore[import]
    build_meta,
    log_agent_error,
)
from backend.config import PathConfig
from backend.models.automation import (
    ArchivingRecord,
    AutomationLog,
    AutomationRule,
    AutomationStatus,
    AutomationTaskType,
    ReclassificationRecord,
)

logger = logging.getLogger(__name__)

# 로그 파일 경로
LOG_DIR = PathConfig.DATA_DIR / "automation_logs"
AUTO_LOG_FILE = LOG_DIR / "automation.jsonl"
RECLASS_LOG_FILE = LOG_DIR / "reclassification.jsonl"
ARCHIVE_LOG_FILE = LOG_DIR / "archiving.jsonl"

# 기존 규칙 파일 경로. 최초 실행에서만 SQLite로 이관하며 원본은 백업한다.
RULES_FILE = LOG_DIR / "automation_rules.jsonl"
_RULES_MIGRATION_ID = "automation_rules_jsonl_to_sqlite_v1"


class AutomationManager:
    """자동화 시스템 관리 서비스"""

    def __init__(self):
        """초기화"""
        # 로그 디렉토리 생성
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            meta = build_meta({"action": "__init__", "log_dir": LOG_DIR.name})
            log_agent_error(logger, "Failed to create log directory", exc, meta)
        # 규칙 CRUD 작업을 직렬화하기 위한 락
        self._rule_lock = threading.Lock()
        # 로그 파일 쓰기 동시성 제어를 위한 락
        self._log_lock = threading.Lock()
        try:
            self._initialize_rule_storage()
            self._migrate_legacy_rules()
        except (OSError, sqlite3.Error) as exc:
            log_agent_error(
                logger,
                "Failed to initialize automation rule storage",
                exc,
                build_meta(
                    {
                        "action": "initialize_automation_rule_storage",
                        "file_name": self._rules_db_path.name,
                    }
                ),
                include_traceback=True,
            )
            raise

    @property
    def _rules_db_path(self) -> Path:
        """기존 규칙 경로와 같은 데이터 디렉터리에 규칙 SQLite DB를 둔다."""
        return Path(RULES_FILE).with_suffix(".db")

    def _connect_rules_db(self) -> sqlite3.Connection:
        self._rules_db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._rules_db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _log_rules_db_error(self, action: str, exc: sqlite3.Error) -> None:
        log_agent_error(
            logger,
            "Automation rule database operation failed",
            exc,
            build_meta({"action": action, "file_name": self._rules_db_path.name}),
            include_traceback=True,
        )

    @staticmethod
    def _rule_db_values(
        rule: AutomationRule,
    ) -> tuple[str, str, str, str, str, int, str]:
        """Convert the validated model to parameterized SQLite column values."""
        data = rule.model_dump(mode="json")
        return (
            rule.rule_id,
            data["name"],
            data["task_type"],
            json.dumps(data["conditions"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(data["actions"], ensure_ascii=False, separators=(",", ":")),
            int(rule.is_active),
            data["created_at"],
        )

    @staticmethod
    def _rule_from_db_row(row: sqlite3.Row) -> AutomationRule:
        """Validate a SQLite row through the public AutomationRule model."""
        is_active = row["is_active"]
        if is_active not in (0, 1):
            raise ValueError("Stored automation rule has an invalid active flag.")
        data = {
            "rule_id": row["rule_id"],
            "name": row["name"],
            "task_type": row["task_type"],
            "conditions": json.loads(row["conditions_json"]),
            "actions": json.loads(row["actions_json"]),
            "is_active": bool(is_active),
            "created_at": row["created_at"],
        }
        return AutomationRule.model_validate(data)

    def _initialize_rule_storage(self) -> None:
        """규칙 및 마이그레이션 테이블을 멱등적으로 준비한다."""
        with closing(self._connect_rules_db()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_rules (
                    rule_id TEXT PRIMARY KEY NOT NULL,
                    name TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    conditions_json TEXT NOT NULL,
                    actions_json TEXT NOT NULL,
                    is_active INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_rule_migrations (
                    migration_id TEXT PRIMARY KEY NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    imported_count INTEGER NOT NULL,
                    malformed_count INTEGER NOT NULL
                )
                """
            )
            connection.commit()

    def _read_legacy_rules(self) -> tuple[List[AutomationRule], int]:
        """마이그레이션할 JSONL을 읽어 유효한 규칙과 손상 행 수를 반환한다."""
        if not RULES_FILE.is_file():
            return [], 0

        rules: List[AutomationRule] = []
        malformed_count = 0
        with open(RULES_FILE, "r", encoding="utf-8") as legacy_file:
            for line in legacy_file:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        malformed_count += 1
                        continue
                    rules.append(AutomationRule.model_validate(data))
                except (json.JSONDecodeError, ValueError, TypeError):
                    malformed_count += 1
        return rules, malformed_count

    def _archive_legacy_rules(self) -> None:
        """성공적으로 이관한 JSONL을 삭제하지 않고 백업 이름으로 보존한다."""
        if not RULES_FILE.is_file():
            return
        backup_path = RULES_FILE.with_name(f"{RULES_FILE.name}.migrated")
        if backup_path.exists():
            logger.warning(
                "Legacy automation rules remain because the migration backup already exists.",
                extra={"action": "archive_legacy_automation_rules"},
            )
            return
        try:
            RULES_FILE.replace(backup_path)
        except OSError as exc:
            log_agent_error(
                logger,
                "Automation rules migrated but legacy backup could not be renamed",
                exc,
                build_meta({"action": "archive_legacy_automation_rules"}),
            )

    def _migrate_legacy_rules(self) -> None:
        """기존 JSONL 규칙을 DB에 한 번 이관하고 원본을 보존한다."""
        if not RULES_FILE.is_file():
            return

        imported_count = 0
        malformed_count = 0
        with closing(self._connect_rules_db()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                migration = connection.execute(
                    "SELECT migration_id FROM automation_rule_migrations WHERE migration_id = ?",
                    (_RULES_MIGRATION_ID,),
                ).fetchone()
                if migration is None:
                    rules, malformed_count = self._read_legacy_rules()
                    for rule in rules:
                        cursor = connection.execute(
                            """
                            INSERT OR IGNORE INTO automation_rules
                                (
                                    rule_id, name, task_type, conditions_json,
                                    actions_json, is_active, created_at
                                )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            self._rule_db_values(rule),
                        )
                        imported_count += cursor.rowcount
                    connection.execute(
                        """
                        INSERT INTO automation_rule_migrations
                            (migration_id, imported_count, malformed_count)
                        VALUES (?, ?, ?)
                        """,
                        (_RULES_MIGRATION_ID, imported_count, malformed_count),
                    )

        if malformed_count:
            logger.warning(
                "Legacy automation rules migration skipped malformed entries.",
                extra={
                    "action": "migrate_legacy_automation_rules",
                    "malformed_count": malformed_count,
                    "imported_count": imported_count,
                },
            )
        self._archive_legacy_rules()

    # ========================================================================
    # 로그 조회
    # ========================================================================

    def get_automation_logs(
        self,
        limit: int = 100,
        task_type: Optional[AutomationTaskType] = None,
        status: Optional[AutomationStatus] = None,
    ) -> List[AutomationLog]:
        """
        자동화 로그 목록 조회

        Args:
            limit: 최대 반환 개수
            task_type: 작업 유형 필터 (선택)
            status: 상태 필터 (선택)

        Returns:
            AutomationLog 리스트 (최신 순)
        """
        # Enum 또는 문자열을 안전하게 문자열로 변환 (Null Safety & Type Safety)
        task_type_str = (
            task_type.value
            if isinstance(task_type, AutomationTaskType)
            else (str(task_type) if task_type is not None else None)
        )
        status_str = (
            status.value
            if isinstance(status, AutomationStatus)
            else (str(status) if status is not None else None)
        )

        logs_data = self._read_jsonl_logs(
            AUTO_LOG_FILE, limit=limit, task_type=task_type_str, status=status_str
        )

        logs = []
        invalid_count = 0
        for data in logs_data:
            if not isinstance(data, dict):
                invalid_count += 1
                continue
            try:
                logs.append(AutomationLog(**data))
            except (ValueError, TypeError):
                invalid_count += 1
                continue

        if invalid_count > 0:
            meta = build_meta(
                {"action": "get_automation_logs", "invalid_count": invalid_count}
            )
            logger.warning(
                "get_automation_logs: %d invalid log record(s) skipped",
                invalid_count,
                extra={"meta": meta},
            )

        return logs

    def get_automation_log_by_id(self, log_id: str) -> Optional[AutomationLog]:
        """
        특정 로그 조회

        Args:
            log_id: 로그 ID

        Returns:
            AutomationLog 또는 None
        """
        if not log_id or not isinstance(log_id, str) or not log_id.strip():
            return None

        # limit 없이 전체 로그 검색 (오래된 로그도 접근 가능)
        logs_data = self._read_jsonl_logs(AUTO_LOG_FILE, limit=None)

        for data in logs_data:
            if not isinstance(data, dict):
                continue
            if data.get("log_id") == log_id:
                try:
                    return AutomationLog(**data)
                except (ValueError, TypeError) as exc:
                    meta = build_meta(
                        {"action": "get_automation_log_by_id", "log_id": log_id}
                    )
                    log_agent_error(logger, "Failed to parse log", exc, meta)
                    return None

        return None

    # ========================================================================
    # 로그 기록 및 태스크 트리거 이력
    # ========================================================================

    def record_automation_log(self, log: AutomationLog) -> bool:
        """
        AutomationLog를 AUTO_LOG_FILE에 안전하게 추가 기록합니다 (Thread-safe append).

        Args:
            log: 기록할 AutomationLog 객체

        Returns:
            성공 시 True, I/O 에러 발생 시 False
        """
        if log is None:
            raise ValueError("log cannot be None")

        with self._log_lock:
            try:
                with open(AUTO_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(log.model_dump_json() + "\n")
                    f.flush()
                return True
            except OSError as exc:
                meta = build_meta(
                    {
                        "action": "record_automation_log",
                        "file_name": AUTO_LOG_FILE.name,
                    },
                    log_id=getattr(log, "log_id", None),
                    task_type=str(getattr(log, "task_type", None)),
                )
                log_agent_error(logger, "Failed to append automation log", exc, meta)
                return False

    def record_task_trigger(
        self,
        task_type: AutomationTaskType,
        task_name: str,
        celery_task_id: str,
        status: AutomationStatus = AutomationStatus.PENDING,
        details: Optional[Dict[str, Any]] = None,
    ) -> AutomationLog:
        """
        수동/외부 자동화 태스크 트리거 이력을 기록합니다.

        Args:
            task_type: 자동화 작업 유형
            task_name: 세부 작업명
            celery_task_id: Celery 비동기 작업 ID
            status: 초기 작업 상태 (기본값: PENDING)
            details: 부가 상세 정보

        Returns:
            생성 및 기록된 AutomationLog 객체
        """
        log = AutomationLog(
            log_id=str(uuid.uuid4()),
            task_type=task_type,
            task_name=task_name,
            celery_task_id=celery_task_id,
            status=status,
            started_at=datetime.now(timezone.utc),
            details=details or {"trigger": "manual_api"},
        )
        self.record_automation_log(log)
        return log

    # ========================================================================
    # 규칙 관리 (SQLite 영속성)
    # ========================================================================

    def _load_all_rules(self) -> List[AutomationRule]:
        """SQLite에서 규칙을 읽고 유효한 AutomationRule만 반환한다."""
        rules: List[AutomationRule] = []
        malformed_count = 0
        with closing(self._connect_rules_db()) as connection:
            rows = connection.execute(
                """
                SELECT
                    rule_id, name, task_type, conditions_json,
                    actions_json, is_active, created_at
                FROM automation_rules ORDER BY rowid
                """
            ).fetchall()
        for row in rows:
            try:
                rules.append(self._rule_from_db_row(row))
            except (json.JSONDecodeError, ValueError, TypeError):
                malformed_count += 1
        if malformed_count:
            logger.warning(
                "SQLite automation rule records failed validation.",
                extra={
                    "action": "load_automation_rules",
                    "malformed_count": malformed_count,
                },
            )
        return rules

    def get_automation_rules(self) -> List[AutomationRule]:
        """
        자동화 규칙 목록 조회 (SQLite 기반).

        Returns:
            저장된 AutomationRule 리스트. 규칙이 없으면 빈 리스트.
        """
        # Serialize reads and writes within this manager; SQLite transactions
        # serialize writes across manager instances and worker processes.
        with self._rule_lock:
            return self._load_all_rules()

    def create_automation_rule(self, rule: AutomationRule) -> AutomationRule:
        """
        자동화 규칙 생성 및 SQLite에 저장.

        Args:
            rule: 생성할 규칙 (rule_id는 호출자가 채워 전달해야 함)

        Returns:
            저장된 규칙 객체

        Raises:
            ValueError: 유효하지 않은 규칙이거나 동일한 rule_id가 이미 존재하는 경우
            sqlite3.Error: 데이터베이스 저장 실패 시
        """
        if not rule or not isinstance(rule, AutomationRule):
            raise ValueError("Valid AutomationRule is required")
        if not rule.rule_id or not rule.rule_id.strip():
            raise ValueError("rule_id must not be empty")

        with self._rule_lock:
            try:
                with closing(self._connect_rules_db()) as connection:
                    with connection:
                        connection.execute("BEGIN IMMEDIATE")
                        connection.execute(
                            """
                            INSERT INTO automation_rules
                                (
                                    rule_id, name, task_type, conditions_json,
                                    actions_json, is_active, created_at
                                )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            self._rule_db_values(rule),
                        )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Rule already exists.") from exc
            except sqlite3.Error as exc:
                self._log_rules_db_error("create_automation_rule", exc)
                raise
            logger.info("[AUTOMATION] 규칙 생성 완료")
            return rule

    def update_automation_rule(
        self, rule_id: str, rule: AutomationRule
    ) -> Optional[AutomationRule]:
        """
        기존 자동화 규칙을 수정하고 저장.

        Args:
            rule_id: 수정 대상 규칙 ID
            rule: 새로운 규칙 데이터

        Returns:
            수정된 규칙 객체 또는 None (rule_id가 존재하지 않는 경우)

        Raises:
            ValueError: rule_id가 비어있거나 rule이 유효하지 않은 경우
            sqlite3.Error: 데이터베이스 저장 실패 시
        """
        if not rule_id or not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError("rule_id must not be empty")
        if not rule or not isinstance(rule, AutomationRule):
            raise ValueError("Valid AutomationRule is required")

        with self._rule_lock:
            updated_rule = rule.model_copy(update={"rule_id": rule_id})
            try:
                with closing(self._connect_rules_db()) as connection:
                    with connection:
                        connection.execute("BEGIN IMMEDIATE")
                        cursor = connection.execute(
                            """
                            UPDATE automation_rules
                            SET name = ?, task_type = ?, conditions_json = ?, actions_json = ?,
                                is_active = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE rule_id = ?
                            """,
                            self._rule_db_values(updated_rule)[1:] + (rule_id,),
                        )
                        if cursor.rowcount == 0:
                            return None
            except sqlite3.Error as exc:
                self._log_rules_db_error("update_automation_rule", exc)
                raise
            logger.info("[AUTOMATION] 규칙 수정 완료")
            return updated_rule

    def delete_automation_rule(self, rule_id: str) -> bool:
        """
        기존 자동화 규칙을 삭제.

        Args:
            rule_id: 삭제 대상 규칙 ID

        Returns:
            삭제 성공 여부 (rule_id가 없거나 빈 값이면 False)

        Raises:
            sqlite3.Error: 데이터베이스 저장 실패 시
        """
        if not rule_id or not isinstance(rule_id, str) or not rule_id.strip():
            return False

        with self._rule_lock:
            try:
                with closing(self._connect_rules_db()) as connection:
                    with connection:
                        connection.execute("BEGIN IMMEDIATE")
                        cursor = connection.execute(
                            "DELETE FROM automation_rules WHERE rule_id = ?",
                            (rule_id,),
                        )
                        if cursor.rowcount == 0:
                            return False
            except sqlite3.Error as exc:
                self._log_rules_db_error("delete_automation_rule", exc)
                raise
            logger.info("[AUTOMATION] 규칙 삭제 완료")
            return True

    # ========================================================================
    # 이력 조회
    # ========================================================================

    def get_reclassification_history(
        self, limit: int = 100
    ) -> List[ReclassificationRecord]:
        """
        재분류 이력 조회

        Args:
            limit: 최대 반환 개수

        Returns:
            ReclassificationRecord 리스트
        """
        records_data = self._read_jsonl_logs(RECLASS_LOG_FILE, limit=limit)

        records = []
        invalid_count = 0
        for data in records_data:
            if not isinstance(data, dict):
                invalid_count += 1
                continue
            try:
                records.append(ReclassificationRecord(**data))
            except (ValueError, TypeError):
                invalid_count += 1
                continue

        if invalid_count > 0:
            meta = build_meta(
                {
                    "action": "get_reclassification_history",
                    "invalid_count": invalid_count,
                }
            )
            logger.warning(
                "get_reclassification_history: %d invalid record(s) skipped",
                invalid_count,
                extra={"meta": meta},
            )

        return records

    def get_archiving_history(self, limit: int = 100) -> List[ArchivingRecord]:
        """
        아카이브 이력 조회

        Args:
            limit: 최대 반환 개수

        Returns:
            ArchivingRecord 리스트
        """
        records_data = self._read_jsonl_logs(ARCHIVE_LOG_FILE, limit=limit)

        records = []
        invalid_count = 0
        for data in records_data:
            if not isinstance(data, dict):
                invalid_count += 1
                continue
            try:
                records.append(ArchivingRecord(**data))
            except (ValueError, TypeError):
                invalid_count += 1
                continue

        if invalid_count > 0:
            meta = build_meta(
                {
                    "action": "get_archiving_history",
                    "invalid_count": invalid_count,
                }
            )
            logger.warning(
                "get_archiving_history: %d invalid record(s) skipped",
                invalid_count,
                extra={"meta": meta},
            )

        return records

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _read_jsonl_logs(
        self,
        file_path: Path,
        limit: Optional[int] = 100,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        JSONL 로그 파일 읽기 (필터링 지원, 최신 순 반환)

        Args:
            file_path: 로그 파일 경로
            limit: 최대 반환 개수 (None이면 전체)
            task_type: 작업 유형 필터 (선택)
            status: 상태 필터 (선택)

        Returns:
            로그 딕셔너리 리스트 (최신 순)
        """
        # limit 검증: None 또는 0 이상의 정수만 허용 (bool 제외) - Fail Fast
        if limit is not None:
            # int 서브클래스 허용, bool 제외
            if isinstance(limit, bool) or not isinstance(limit, int):
                raise TypeError("limit must be a non-boolean int or None")
            if limit < 0:
                raise ValueError("limit must be non-negative")

        if not file_path:
            return []

        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        if not file_path.exists():
            return []

        logs = []
        parse_error_count = 0
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        log_data = json.loads(line)
                        if not isinstance(log_data, dict):
                            parse_error_count += 1
                            continue

                        # 필터링
                        if task_type and log_data.get("task_type") != task_type:
                            continue
                        if status and log_data.get("status") != status:
                            continue

                        logs.append(log_data)

                    except (json.JSONDecodeError, UnicodeDecodeError):
                        parse_error_count += 1
                        continue

            if parse_error_count > 0:
                logger.warning(
                    "_read_jsonl_logs: %d malformed line(s) skipped in '%s'",
                    parse_error_count,
                    file_path.name,
                )

        except OSError as exc:
            meta = build_meta(
                {"action": "_read_jsonl_logs", "file_name": file_path.name}
            )
            log_agent_error(logger, "Failed to read log file", exc, meta)

        # 최신 로그가 먼저 오도록 역순 iterator 사용
        reversed_logs = reversed(logs)
        if limit is not None:
            # limit이 작은 경우 전체 역순 리스트를 만들지 않고 슬라이스
            return list(islice(reversed_logs, limit))
        # limit이 None이면 전체를 최신 순으로 반환
        return list(reversed_logs)


# 싱글톤 인스턴스
automation_manager = AutomationManager()

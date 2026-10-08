# backend/services/automation_manager.py

"""
Automation Manager Service
자동화 로그, 규칙, 이력 관리를 위한 서비스 레이어
"""

import json
import logging
import threading
from itertools import islice
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

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

# 규칙 저장 파일 경로 (MVP: JSONL 기반 경량 영속성. 향후 DB 연동 시 교체)
RULES_FILE = LOG_DIR / "automation_rules.jsonl"


class AutomationManager:
    """자동화 시스템 관리 서비스"""

    def __init__(self):
        """초기화"""
        # 로그 디렉토리 생성
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # 규칙 CRUD 작업을 직렬화하기 위한 락
        self._rule_lock = threading.Lock()

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
        # Enum을 문자열로 변환
        task_type_str = task_type.value if task_type else None
        status_str = status.value if status else None

        logs_data = self._read_jsonl_logs(
            AUTO_LOG_FILE, limit=limit, task_type=task_type_str, status=status_str
        )

        logs = []
        for data in logs_data:
            try:
                logs.append(AutomationLog(**data))
            except (ValueError, TypeError, ValidationError) as exc:
                meta = build_meta(
                    {"action": "get_automation_logs", "log_id": data.get("log_id")}
                )
                log_agent_error(logger, "Invalid log data", exc, meta)
                continue

        return logs

    def get_automation_log_by_id(self, log_id: str) -> Optional[AutomationLog]:
        """
        특정 로그 조회

        Args:
            log_id: 로그 ID

        Returns:
            AutomationLog 또는 None
        """
        # limit 없이 전체 로그 검색 (오래된 로그도 접근 가능)
        logs_data = self._read_jsonl_logs(AUTO_LOG_FILE, limit=None)

        for data in logs_data:
            if data.get("log_id") == log_id:
                try:
                    return AutomationLog(**data)
                except (ValueError, TypeError, ValidationError) as exc:
                    meta = build_meta(
                        {"action": "get_automation_log_by_id", "log_id": log_id}
                    )
                    log_agent_error(logger, "Failed to parse log", exc, meta)
                    return None

        return None

    # ========================================================================
    # 규칙 관리 (MVP: JSONL 파일 기반 경량 영속성. 향후 DB 연동 시 이 섹션 전체를 교체)
    # ========================================================================

    def _load_all_rules(self) -> List[AutomationRule]:
        """
        JSONL 규칙 파일에서 모든 규칙을 로드한다.
        파싱 실패한 항목은 로그를 남기고 건너뛴다.
        """
        rules: List[AutomationRule] = []
        if not RULES_FILE.exists():
            return rules
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rules.append(AutomationRule(**json.loads(line)))
                    except (
                        json.JSONDecodeError,
                        ValueError,
                        TypeError,
                        ValidationError,
                    ) as exc:
                        meta = build_meta({"action": "_load_all_rules"})
                        log_agent_error(
                            logger, "Malformed rule entry skipped", exc, meta
                        )
        except OSError as exc:
            meta = build_meta({"action": "_load_all_rules", "file": RULES_FILE.name})
            log_agent_error(logger, "Failed to read rules file", exc, meta)
        return rules

    def _persist_all_rules(self, rules: List[AutomationRule]) -> None:
        """
        규칙 목록 전체를 RULES_FILE에 덮어씌운다 (rewrite-on-update 패턴).
        MVP 규모에서는 규칙 수가 충분히 적어 전체 재기록이 안전하다.
        임시 파일에 쓰고 성공 시 원자적으로 교체하여 파일 손상을 방지한다.
        """
        try:
            temp_file = RULES_FILE.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                for rule in rules:
                    f.write(rule.model_dump_json() + "\n")
                f.flush()
            temp_file.replace(RULES_FILE)
        except OSError as exc:
            meta = build_meta({"action": "_persist_all_rules", "file": RULES_FILE.name})
            log_agent_error(logger, "Failed to persist rules", exc, meta)
            raise

    def get_automation_rules(self) -> List[AutomationRule]:
        """
        자동화 규칙 목록 조회 (JSONL 파일 기반).

        Returns:
            저장된 AutomationRule 리스트. 파일이 없으면 빈 리스트.
        """
        return self._load_all_rules()

    def create_automation_rule(self, rule: AutomationRule) -> AutomationRule:
        """
        자동화 규칙 생성 및 JSONL 파일에 저장.

        Args:
            rule: 생성할 규칙 (rule_id는 호출자가 채워 전달해야 함)

        Returns:
            저장된 규칙 객체

        Raises:
            ValueError: 동일한 rule_id가 이미 존재하는 경우
            OSError: 파일 쓰기 실패 시
        """
        with self._rule_lock:
            existing = self._load_all_rules()
            if any(r.rule_id == rule.rule_id for r in existing):
                raise ValueError(f"Rule already exists: {rule.rule_id}")
            existing.append(rule)
            self._persist_all_rules(existing)
            logger.info("[AUTOMATION] 규칙 생성 완료 (rule_id=%s)", rule.rule_id)
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
            OSError: 파일 쓰기 실패 시
        """
        with self._rule_lock:
            existing = self._load_all_rules()
            updated: List[AutomationRule] = []
            found = False
            for r in existing:
                if r.rule_id == rule_id:
                    rule.rule_id = rule_id  # 경로 파라미터와 불일치 방지
                    updated.append(rule)
                    found = True
                else:
                    updated.append(r)
            if not found:
                return None
            self._persist_all_rules(updated)
            logger.info("[AUTOMATION] 규칙 수정 완료 (rule_id=%s)", rule_id)
            return rule

    def delete_automation_rule(self, rule_id: str) -> bool:
        """
        기존 자동화 규칙을 삭제.

        Args:
            rule_id: 삭제 대상 규칙 ID

        Returns:
            삭제 성공 여부 (rule_id가 없으면 False)

        Raises:
            OSError: 파일 쓰기 실패 시
        """
        with self._rule_lock:
            existing = self._load_all_rules()
            filtered = [r for r in existing if r.rule_id != rule_id]
            if len(filtered) == len(existing):
                return False
            self._persist_all_rules(filtered)
            logger.info("[AUTOMATION] 규칙 삭제 완료 (rule_id=%s)", rule_id)
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
        for data in records_data:
            try:
                records.append(ReclassificationRecord(**data))
            except (ValueError, TypeError, ValidationError) as exc:
                meta = build_meta(
                    {
                        "action": "get_reclassification_history",
                        "record_id": data.get("record_id"),
                    }
                )
                log_agent_error(logger, "Invalid reclassification record", exc, meta)
                continue

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
        for data in records_data:
            try:
                records.append(ArchivingRecord(**data))
            except (ValueError, TypeError, ValidationError) as exc:
                meta = build_meta(
                    {
                        "action": "get_archiving_history",
                        "record_id": data.get("record_id"),
                    }
                )
                log_agent_error(logger, "Invalid archiving record", exc, meta)
                continue

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
        if not file_path.exists():
            return []

        logs = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        log_data = json.loads(line)

                        # 필터링
                        if task_type and log_data.get("task_type") != task_type:
                            continue
                        if status and log_data.get("status") != status:
                            continue

                        logs.append(log_data)

                    except json.JSONDecodeError:
                        logger.warning(
                            "Malformed JSON line in %s", Path(file_path).name
                        )
                        continue

        except OSError as exc:
            meta = build_meta(
                {"action": "_read_jsonl_logs", "file_name": file_path.name}
            )
            log_agent_error(
                logger, f"Failed to read log file: {file_path.name}", exc, meta
            )

        # limit 검증: None 또는 0 이상의 정수만 허용 (bool 제외)
        if limit is not None:
            # int 서브클래스 허용, bool 제외
            if isinstance(limit, bool) or not isinstance(limit, int):
                raise TypeError("limit must be a non-boolean int or None")
            if limit < 0:
                raise ValueError("limit must be non-negative")
        # 최신 로그가 먼저 오도록 역순 iterator 사용
        reversed_logs = reversed(logs)
        if limit is not None:
            # limit이 작은 경우 전체 역순 리스트를 만들지 않고 슬라이스
            return list(islice(reversed_logs, limit))
        # limit이 None이면 전체를 최신 순으로 반환
        return list(reversed_logs)


# 싱글톤 인스턴스
automation_manager = AutomationManager()

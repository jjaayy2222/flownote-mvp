# backend/services/automation_manager.py

"""
Automation Manager Service
자동화 로그, 규칙, 이력 관리를 위한 서비스 레이어
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from backend.config import PathConfig
from backend.models.automation import (
    AutomationLog,
    AutomationRule,
    AutomationTaskType,
    AutomationStatus,
    ReclassificationRecord,
    ArchivingRecord,
)

logger = logging.getLogger(__name__)

# 로그 파일 경로
LOG_DIR = PathConfig.DATA_DIR / "automation_logs"
AUTO_LOG_FILE = LOG_DIR / "automation.jsonl"
RECLASS_LOG_FILE = LOG_DIR / "reclassification.jsonl"
ARCHIVE_LOG_FILE = LOG_DIR / "archiving.jsonl"


class AutomationManager:
    """자동화 시스템 관리 서비스"""

    def __init__(self):
        """초기화"""
        # 로그 디렉토리 생성
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ========================================================================
    # 로그 조회
    # ========================================================================

    def get_automation_logs(
        self,
        limit: int = 100,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[AutomationLog]:
        """
        자동화 로그 목록 조회

        Args:
            limit: 최대 반환 개수
            task_type: 작업 유형 필터 (선택)
            status: 상태 필터 (선택)

        Returns:
            AutomationLog 리스트
        """
        logs_data = self._read_jsonl_logs(
            AUTO_LOG_FILE, limit=limit, task_type=task_type, status=status
        )

        logs = []
        for data in logs_data:
            try:
                logs.append(AutomationLog(**data))
            except Exception as exc:
                logger.warning(
                    "Invalid log data",
                    exc_info=False,
                    extra={"error_type": type(exc).__name__},
                )
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
        logs_data = self._read_jsonl_logs(AUTO_LOG_FILE, limit=10000)

        for data in logs_data:
            if data.get("log_id") == log_id:
                try:
                    return AutomationLog(**data)
                except Exception as exc:
                    logger.error(
                        "Failed to parse log",
                        exc_info=False,
                        extra={"log_id": log_id, "error_type": type(exc).__name__},
                    )
                    return None

        return None

    # ========================================================================
    # 규칙 관리 (현재는 Stub - DB 연동 필요)
    # ========================================================================

    def get_automation_rules(self) -> List[AutomationRule]:
        """
        자동화 규칙 목록 조회

        Returns:
            AutomationRule 리스트 (현재는 빈 리스트)
        """
        # TODO: DB 연동 후 실제 규칙 조회 구현
        logger.info("get_automation_rules called (stub)")
        return []

    def create_automation_rule(self, rule: AutomationRule) -> AutomationRule:
        """
        자동화 규칙 생성

        Args:
            rule: 생성할 규칙

        Returns:
            생성된 규칙

        Raises:
            NotImplementedError: DB 연동 전
        """
        # TODO: DB 연동 후 규칙 저장 구현
        logger.warning("create_automation_rule called (not implemented)")
        raise NotImplementedError("Rule creation requires database integration")

    def update_automation_rule(
        self, rule_id: str, rule: AutomationRule
    ) -> Optional[AutomationRule]:
        """
        자동화 규칙 수정

        Args:
            rule_id: 규칙 ID
            rule: 수정할 규칙 데이터

        Returns:
            수정된 규칙 또는 None

        Raises:
            NotImplementedError: DB 연동 전
        """
        # TODO: DB 연동 후 규칙 수정 구현
        logger.warning(f"update_automation_rule called for {rule_id} (not implemented)")
        raise NotImplementedError("Rule update requires database integration")

    def delete_automation_rule(self, rule_id: str) -> bool:
        """
        자동화 규칙 삭제

        Args:
            rule_id: 규칙 ID

        Returns:
            삭제 성공 여부

        Raises:
            NotImplementedError: DB 연동 전
        """
        # TODO: DB 연동 후 규칙 삭제 구현
        logger.warning(f"delete_automation_rule called for {rule_id} (not implemented)")
        raise NotImplementedError("Rule deletion requires database integration")

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
            except Exception as exc:
                logger.warning(
                    "Invalid reclassification record",
                    exc_info=False,
                    extra={"error_type": type(exc).__name__},
                )
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
            except Exception as exc:
                logger.warning(
                    "Invalid archiving record",
                    exc_info=False,
                    extra={"error_type": type(exc).__name__},
                )
                continue

        return records

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _read_jsonl_logs(
        self,
        file_path: Path,
        limit: int = 100,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        JSONL 로그 파일 읽기 (필터링 지원)

        Args:
            file_path: 로그 파일 경로
            limit: 최대 반환 개수
            task_type: 작업 유형 필터 (선택)
            status: 상태 필터 (선택)

        Returns:
            로그 딕셔너리 리스트
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

                        if len(logs) >= limit:
                            break

                    except json.JSONDecodeError:
                        logger.warning(f"Malformed JSON line in {file_path}")
                        continue

        except Exception as exc:
            logger.error(
                f"Failed to read log file: {file_path}",
                exc_info=False,
                extra={"error_type": type(exc).__name__},
            )

        return logs


# 싱글톤 인스턴스
automation_manager = AutomationManager()

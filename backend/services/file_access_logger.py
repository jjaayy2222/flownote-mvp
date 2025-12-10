# backend/services/file_access_logger.py

"""
FileAccessLogger - 파일 접근 이력 관리 서비스
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import Counter

logger = logging.getLogger(__name__)


class FileAccessLogger:
    """
    파일 접근 이력을 CSV 파일에 기록하고 통계를 제공하는 서비스.
    """

    def __init__(self, log_dir: str = "data", log_file: str = "file_access_logs.csv"):
        """
        초기화

        Args:
            log_dir: 로그 파일 저장 디렉토리 (프로젝트 루트 기준 상대 경로)
            log_file: 로그 파일명
        """
        # 프로젝트 루트 경로 추론 (이 파일은 backend/services/ 에 위치)
        self.project_root = Path(__file__).parent.parent.parent
        self.log_path = self.project_root / log_dir / log_file
        self.fieldnames = ["timestamp", "file_path", "access_type"]

        # 로그 파일 초기화
        self._ensure_log_file()

    def _ensure_log_file(self):
        """로그 파일이 없으면 생성하고 헤더를 작성"""
        if not self.log_path.exists():
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                    writer.writeheader()
                logger.info(f"Created new access log file: {self.log_path}")
            except Exception as e:
                logger.error(f"Failed to create access log file: {e}")

    def log_access(self, file_path: str, access_type: str = "read") -> bool:
        """
        파일 접근 이력 기록

        Args:
            file_path: 접근한 파일 경로
            access_type: 접근 유형 ("read", "write", "create", "delete", "classify")

        Returns:
            bool: 성공 여부
        """
        try:
            timestamp = datetime.now().isoformat()

            with open(self.log_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writerow(
                    {
                        "timestamp": timestamp,
                        "file_path": str(file_path),
                        "access_type": access_type,
                    }
                )
            return True
        except Exception as e:
            logger.error(f"Failed to log file access for {file_path}: {e}")
            return False

    def get_file_stats(self, file_path: str) -> Dict[str, Any]:
        """
        특정 파일의 접근 통계 반환

        Args:
            file_path: 분석할 파일 경로

        Returns:
            Dict: {
                "access_count": int,
                "last_accessed": str (ISO format),
                "access_types": Dict[str, int] (Type별 횟수)
            }
        """
        stats = {"access_count": 0, "last_accessed": None, "access_types": Counter()}

        if not self.log_path.exists():
            return stats

        try:
            target_path = str(file_path)
            with open(self.log_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["file_path"] == target_path:
                        stats["access_count"] += 1
                        stats["last_accessed"] = row[
                            "timestamp"
                        ]  # 순차적으로 읽으므로 마지막 값이 최신
                        stats["access_types"][row["access_type"]] += 1

            # Counter를 dict로 변환
            stats["access_types"] = dict(stats["access_types"])
            return stats

        except Exception as e:
            logger.error(f"Failed to get stats for {file_path}: {e}")
            return stats

    def get_top_accessed_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        가장 많이 접근한 파일 목록 반환

        Args:
            limit: 반환할 파일 개수

        Returns:
            List[Dict]: [{"file_path": str, "count": int}, ...]
        """
        if not self.log_path.exists():
            return []

        try:
            counter = Counter()
            with open(self.log_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    counter[row["file_path"]] += 1

            # 상위 limit개 추출
            top_files = [
                {"file_path": path, "count": count}
                for path, count in counter.most_common(limit)
            ]
            return top_files

        except Exception as e:
            logger.error(f"Failed to get top accessed files: {e}")
            return []

    def get_recent_files(self, days: int = 7) -> List[str]:
        """
        최근 N일 이내에 접근된 파일 목록 반환 (중복 제거)

        Args:
            days: 기간 (일 단위)

        Returns:
            List[str]: 파일 경로 목록
        """
        if not self.log_path.exists():
            return []

        recent_files = set()
        cutoff_date = datetime.now().timestamp() - (days * 24 * 60 * 60)

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        # ISO format string to timestamp
                        log_time = datetime.fromisoformat(row["timestamp"]).timestamp()
                        if log_time >= cutoff_date:
                            recent_files.add(row["file_path"])
                    except ValueError:
                        continue

            return list(recent_files)
        except Exception as e:
            logger.error(f"Failed to get recent files: {e}")
            return []

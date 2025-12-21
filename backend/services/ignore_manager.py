# backend/services/ignore_manager.py

import time
import threading
from pathlib import Path
from typing import Dict, Optional


class IgnoreManager:
    """
    파일 이벤트 루프 방지를 위한 무시 목록 관리자
    일시적으로 특정 경로에 대한 이벤트를 무시합니다.
    """

    def __init__(self):
        self._ignores: Dict[str, float] = {}  # path -> expiration_timestamp
        self._lock = threading.Lock()

    def _normalize_path(self, path: str) -> str:
        """
        경로를 정규화하여 일관된 문자열 포맷으로 반환합니다.
        절대 경로 변환 실패 시 원본 문자열을 반환합니다.
        """
        try:
            return str(Path(path).resolve())
        except (OSError, ValueError):
            # 파일 시스템 접근 불가 등의 사유로 resolve 실패 시 원본 사용
            return str(path)

    def add(self, path: str, duration: float = 2.0):
        """특정 경로를 duration(초) 동안 무시 목록에 추가"""
        resolved_path = self._normalize_path(path)
        with self._lock:
            self._ignores[resolved_path] = time.time() + duration
            # Cleanup expired items casually
            self._cleanup()

    def is_ignored(self, path: str) -> bool:
        """현재 경로가 무시되어야 하는지 확인"""
        path_str = self._normalize_path(path)
        with self._lock:
            if path_str not in self._ignores:
                return False

            # Check expiration
            if time.time() > self._ignores[path_str]:
                # Expired
                del self._ignores[path_str]
                return False
            return True

    def _cleanup(self):
        """만료된 항목 정리"""
        now = time.time()
        # Create list of keys to remove to avoid runtime error during iteration
        expired = [p for p, t in self._ignores.items() if now > t]
        for p in expired:
            if p in self._ignores:
                del self._ignores[p]


# Global Ignore Manager instance
ignore_manager = IgnoreManager()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/search_history.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - 검색 히스토리 관리
[EN] FlowNote MVP - Search History Management
"""

import copy
import json
import logging
import os
import stat
import tempfile
import threading
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, TypedDict

try:
    import fcntl

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

from backend.utils.common import format_error_msg

logger = logging.getLogger(__name__)

# [KO] 최대 보관 검색 기록 수 기본값 (디스크 공간 제약 방어)
# [EN] Default maximum number of search history entries to keep (bounds disk footprint)
DEFAULT_MAX_HISTORY_ENTRIES = 1000


def _custom_json_serializer(obj: Any) -> str:
    """JSON 직렬화 불가 객체를 위한 커스텀 직렬화 헬퍼"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


class SearchStatistics(TypedDict):
    """
    [KO] 검색 통계 반환 타입
    [EN] Return type for search statistics
    """

    total_searches: int
    avg_results: float
    most_common_query: Optional[str]


class SearchHistory:
    """
    [KO] 검색 히스토리를 로컬 JSON 파일에 영속화하고 관리하는 클래스.
    [EN] A class to persist and manage search history in a local JSON file.
    """

    # [KO] 프로세스 내 스레드 간 직렬화를 위한 재진입 락 및 재진입 깊이 추적
    # [EN] Reentrant lock to serialize threads within a process and track reentrancy depth
    _lock = threading.RLock()
    _lock_depth = threading.local()

    def __init__(
        self,
        storage_path: str = "data/search_history.json",
        max_history_entries: int = DEFAULT_MAX_HISTORY_ENTRIES,
        user_id: Optional[str] = None,
    ):
        """
        [KO]
        히스토리 저장 경로를 설정하고 기존 데이터를 로드합니다.

        Args:
            storage_path: 히스토리를 저장할 JSON 파일 경로
            max_history_entries: 보관할 최대 검색 기록 수 (양의 정수)
            user_id: 특정 사용자에 한정하여 격리 관리할 사용자 식별자 (선택 사항)

        [EN]
        Sets the history storage path and loads existing data.

        Args:
            storage_path: JSON file path to store history
            max_history_entries: Maximum number of search history entries to keep (positive int)
            user_id: Optional user identifier to partition/isolate history records
        """
        if max_history_entries <= 0:
            raise ValueError(
                f"max_history_entries must be a positive integer, got {max_history_entries}"
            )
        self.storage_path = storage_path
        self.max_history_entries = max_history_entries
        self.user_id = user_id
        self.history: Dict[str, Dict] = {}
        with self._interprocess_lock():
            self._load_history()

    def _validate_and_resolve_storage_path(self) -> str:
        """
        [KO] 저장 경로의 심볼릭 링크를 검증하고 안전한 대상 경로를 반환합니다.
             심볼릭 링크가 신뢰할 수 있는 기본 디렉토리 외부를 가리키면 보안 예외를 발생시킵니다.
        [EN] Validates storage_path symlinks and returns a safe destination path.
             Rejects symlinks pointing outside the trusted base directory.
        """
        abs_path = os.path.abspath(self.storage_path)
        trusted_dir = os.path.realpath(os.path.dirname(abs_path) or ".")
        real_path = os.path.realpath(abs_path)

        if os.path.islink(abs_path):
            try:
                common = os.path.commonpath([trusted_dir, real_path])
                if common != trusted_dir:
                    raise PermissionError(
                        f"보안 경고: 신뢰할 수 없는 디렉토리를 가리키는 심볼릭 링크 거부: {self.storage_path} -> {real_path}"
                    )
            except ValueError:
                raise PermissionError(
                    f"보안 경고: 신뢰할 수 없는 경로를 가리키는 심볼릭 링크 거부: {self.storage_path}"
                )
        return real_path

    @contextmanager
    def _interprocess_lock(self):
        """
        [KO] 프로세스 간(fcntl.flock) 및 스레드 간(_lock) 배타적 잠금을 제공하는 컨텍스트 매니저.
        [EN] Context manager providing cross-process (fcntl.flock) and cross-thread (_lock) synchronization.
        """
        with SearchHistory._lock:
            if not HAS_FCNTL:
                yield
                return

            current_depth = getattr(SearchHistory._lock_depth, "depth", 0)
            if current_depth > 0:
                # 동일 스레드 내 재진입인 경우 이미 flock이 획득되어 있으므로 중복 flock을 피함
                SearchHistory._lock_depth.depth = current_depth + 1
                try:
                    yield
                finally:
                    SearchHistory._lock_depth.depth -= 1
                return

            try:
                target_path = self._validate_and_resolve_storage_path()
            except PermissionError:
                target_path = os.path.abspath(self.storage_path)

            lock_dir = os.path.dirname(target_path) or "."
            if lock_dir != ".":
                try:
                    os.makedirs(lock_dir, exist_ok=True)
                except OSError:
                    pass
            lock_path = f"{target_path}.lock"

            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            except OSError as e:
                logger.error(f"락 파일 생성 실패: {e}")
                yield
                return

            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                SearchHistory._lock_depth.depth = 1
                try:
                    yield
                finally:
                    SearchHistory._lock_depth.depth = 0
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _refresh_history(self) -> bool:
        """
        [KO] 디스크에서 최신 히스토리를 읽어와 메모리를 동기화합니다. (락 내부에서 호출)
        [EN] Refreshes in-memory history from disk. (Must be called under lock)
        """
        try:
            target_path = self._validate_and_resolve_storage_path()
        except PermissionError as e:
            logger.error(f"저장 경로 검증 실패: {e}")
            return False

        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                self._prune_history()
                return True
            except (OSError, ValueError) as e:
                logger.error(
                    f"히스토리 갱신 실패: {type(e).__name__}: {format_error_msg(e)}",
                    extra={
                        "action": "refresh_history",
                        "path": self.storage_path,
                        "error_type": type(e).__name__,
                    },
                )
                return False
        return True

    def _prune_history(self) -> None:
        """
        [KO] 최대 보관 수를 초과할 경우 오래된 검색 기록을 정리하여 디스크 공간을 제한합니다.
        [EN] Prunes older search records when exceeding maximum entries to bound disk usage.
        """
        if len(self.history) > self.max_history_entries:
            sorted_items = sorted(
                self.history.items(),
                key=lambda x: x[1].get("search_time", ""),
                reverse=True,
            )
            self.history = dict(sorted_items[: self.max_history_entries])

    def _load_history(self):
        """
        [KO]
        지정된 경로에서 저장된 검색 히스토리를 로드합니다. 파일이 없으면 디렉터리를 생성합니다.

        [EN]
        Loads saved search history from the specified path. Creates directory if it doesn't exist.
        """
        try:
            target_path = self._validate_and_resolve_storage_path()
        except PermissionError as e:
            logger.error(f"보안 오류로 히스토리 로드 실패: {e}")
            self.history = {}
            return

        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                self._prune_history()
            except (OSError, ValueError) as e:
                logger.warning(
                    f"히스토리 로드 실패: {type(e).__name__}: {format_error_msg(e)}",
                    extra={
                        "action": "load_history",
                        "path": self.storage_path,
                        "error_type": type(e).__name__,
                    },
                )
                self.history = {}
        else:
            storage_dir = os.path.dirname(target_path) or "."
            if storage_dir != ".":
                os.makedirs(storage_dir, exist_ok=True)
            self.history = {}

    def _save_history(self) -> bool:
        """
        [KO]
        메모리의 히스토리 데이터를 JSON 파일에 안전하게 저장합니다.
        원자적 교체, 소유자 전용 권한 설정(0o600), 임시 파일 정리를 보장합니다.

        Returns:
            저장 성공 시 True, 직렬화 또는 I/O 실패 시 False

        [EN]
        Safely saves in-memory history data to a JSON file.
        Guarantees atomic replacement, owner-only permissions (0o600), and tempfile cleanup.

        Returns:
            True if saved successfully, False on serialization or I/O failure.
        """
        self._prune_history()

        # 1단계: 직렬화
        try:
            serialized = json.dumps(
                self.history,
                ensure_ascii=False,
                indent=2,
                default=_custom_json_serializer,
            )
        except (TypeError, ValueError) as e:
            logger.error(
                f"히스토리 직렬화 실패: {type(e).__name__}: {format_error_msg(e)}",
                extra={
                    "action": "save_history_serialize",
                    "path": self.storage_path,
                    "error_type": type(e).__name__,
                },
            )
            return False

        # 2단계: 대상 경로 해석 및 검증
        try:
            target_path = self._validate_and_resolve_storage_path()
        except PermissionError as e:
            logger.error(f"보안 오류로 저장 실패: {e}")
            return False

        storage_dir = os.path.dirname(target_path) or "."
        target_exists = os.path.exists(target_path)
        target_stat = None
        if target_exists:
            try:
                target_stat = os.stat(target_path)
            except OSError:
                pass

        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=storage_dir,
                delete=False,
                suffix=".tmp",
            ) as tmp_f:
                tmp_path = tmp_f.name
                tmp_f.write(serialized)

            # 권한 복제 또는 소유자 전용 0o600 강제 (개인정보 보호)
            if target_stat is not None:
                try:
                    os.chmod(tmp_path, stat.S_IMODE(target_stat.st_mode))
                except OSError:
                    pass
            else:
                try:
                    os.chmod(tmp_path, 0o600)
                except OSError:
                    pass

            os.replace(tmp_path, target_path)
            return True

        except (OSError, UnicodeEncodeError) as e:
            logger.error(
                f"히스토리 저장 실패: {type(e).__name__}: {format_error_msg(e)}",
                extra={
                    "action": "save_history_write",
                    "path": self.storage_path,
                    "error_type": type(e).__name__,
                },
            )
            return False

        finally:
            if tmp_path is not None and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _apply_and_persist(
        self,
        mutate: Callable[[], object],
        rollback: Callable[[], object],
        rollback_msg: str,
        action: str,
    ) -> bool:
        """
        [KO]
        락 획득 → 디스크 최신 상태 동기화 → 스냅샷 캡처 → 뮤테이션 → 저장 → 실패 시 원복을 수행합니다.

        Args:
            mutate: 메모리 상태를 변경하는 함수
            rollback: 보조 롤백 함수
            rollback_msg: 롤백 시 로그에 남길 메시지
            action: 로그 extra에 포함할 액션 식별자

        Returns:
            영속화 성공 시 True, 실패(롤백 완료) 시 False

        [EN]
        Acquires lock -> reconciles from disk -> captures snapshot -> mutates -> saves -> rolls back on failure.
        """
        with self._interprocess_lock():
            # 1. 디스크 최신 상태와 동기화
            if not self._refresh_history():
                logger.error(
                    "디스크 히스토리 조정 실패로 영속화가 취소되었습니다.",
                    extra={"action": action, "error_type": "reconcile_failure"},
                )
                return False

            # 2. 락 내부에서 프루닝/뮤테이션 전 전체 스냅샷 캡처
            snapshot_before = copy.deepcopy(self.history)

            # 3. 변경 적용
            try:
                mutate()
            except Exception as e:
                self.history = snapshot_before
                logger.error(f"뮤테이션 적용 실패: {e}")
                return False

            # 4. 저장 시도
            if self._save_history():
                return True

            # 5. 저장 실패 시 완전한 이전 스냅샷 복원
            self.history = snapshot_before
            try:
                rollback()
            except Exception:
                pass
            logger.error(
                rollback_msg,
                extra={"action": action, "error_type": "save_failure"},
            )
            return False

    def add_search(
        self, query: str, results_count: int, top_results: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        [KO]
        새로운 검색 기록을 추가하고 영속화합니다.

        Args:
            query: 검색에 사용된 쿼리 문자열
            results_count: 검색된 결과의 총 개수
            top_results: 상위 검색 결과 미리보기 텍스트 리스트

        Returns:
            저장 성공 시 새로 생성된 검색 고유 ID, 실패 시 None
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        search_id = f"search_{timestamp}_{unique_id}"
        record = {
            "query": query,
            "results_count": results_count,
            "top_results": top_results[:3] if top_results else [],
            "search_time": datetime.now().isoformat(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": self.user_id,
        }

        persisted = self._apply_and_persist(
            mutate=lambda: self.history.update({search_id: record}),
            rollback=lambda: self.history.pop(search_id, None),
            rollback_msg="히스토리 저장 실패로 검색 기록 추가가 취소되었습니다.",
            action="add_search_rollback",
        )
        if not persisted or search_id not in self.history:
            return None
        return search_id

    def get_search(self, search_id: str) -> Optional[Dict]:
        """
        [KO] 특정 검색 ID의 기록을 조회합니다. 사용자 ID가 설정된 경우 격리 검증을 수행합니다.
        """
        with self._interprocess_lock():
            self._refresh_history()
            record = self.history.get(search_id)
            if (
                record
                and self.user_id is not None
                and record.get("user_id") != self.user_id
            ):
                return None
            return record

    def get_recent_searches(self, limit: int = 10) -> List[Dict]:
        """
        [KO] 최근 수행된 검색 기록들을 최신순으로 정렬하여 조회합니다.
        """
        with self._interprocess_lock():
            self._refresh_history()
            user_items = [
                (sid, info)
                for sid, info in self.history.items()
                if self.user_id is None or info.get("user_id") == self.user_id
            ]
            sorted_history = sorted(
                user_items, key=lambda x: x[1]["search_time"], reverse=True
            )
            return [{"id": sid, **info} for sid, info in sorted_history[:limit]]

    def get_all_searches(self) -> Dict[str, Dict]:
        """
        [KO] 저장된 모든 검색 기록을 조회합니다. 사용자 ID가 설정된 경우 격리 조회합니다.
        """
        with self._interprocess_lock():
            self._refresh_history()
            if self.user_id is None:
                return dict(self.history)
            return {
                sid: info
                for sid, info in self.history.items()
                if info.get("user_id") == self.user_id
            }

    def delete_search(self, search_id: str) -> bool:
        """
        [KO] 특정 검색 ID의 기록을 삭제합니다. 디스크 갱신 후 삭제 대상을 확인합니다.
        """
        with self._interprocess_lock():
            if not self._refresh_history():
                return False
            if search_id not in self.history:
                return False
            record = self.history[search_id]
            if self.user_id is not None and record.get("user_id") != self.user_id:
                return False

            return self._apply_and_persist(
                mutate=lambda: self.history.pop(search_id, None),
                rollback=lambda: self.history.update({search_id: record}),
                rollback_msg="히스토리 저장 실패로 검색 기록 삭제가 취소되었습니다.",
                action="delete_search_rollback",
            )

    def clear_all(self) -> bool:
        """
        [KO] 검색 기록을 삭제합니다. user_id 설정 시 해당 사용자의 기록만 삭제합니다.
        """
        with self._interprocess_lock():
            if not self._refresh_history():
                return False

            def _mutate():
                if self.user_id is None:
                    self.history.clear()
                else:
                    self.history = {
                        k: v
                        for k, v in self.history.items()
                        if v.get("user_id") != self.user_id
                    }

            return self._apply_and_persist(
                mutate=_mutate,
                rollback=lambda: None,
                rollback_msg="히스토리 저장 실패로 전체 삭제가 취소되었습니다.",
                action="clear_all_rollback",
            )

    def get_statistics(self) -> SearchStatistics:
        """
        [KO] 검색 통계 정보를 계산합니다. user_id 격리를 지원합니다.
        """
        with self._interprocess_lock():
            self._refresh_history()
            user_records = [
                h
                for h in self.history.values()
                if self.user_id is None or h.get("user_id") == self.user_id
            ]
            if not user_records:
                return {
                    "total_searches": 0,
                    "avg_results": 0.0,
                    "most_common_query": None,
                }

            total_searches = len(user_records)
            avg_results = sum(h["results_count"] for h in user_records) / total_searches
            query_counts = Counter(h["query"] for h in user_records)
            top_queries = query_counts.most_common(1)
            most_common = top_queries[0][0] if top_queries else None

            return {
                "total_searches": total_searches,
                "avg_results": round(avg_results, 1),
                "most_common_query": most_common,
            }

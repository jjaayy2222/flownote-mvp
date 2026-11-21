# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/search_history.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - 검색 히스토리 관리
[EN] FlowNote MVP - Search History Management
"""

import copy
import errno
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Callable, Dict, Generator, List, Optional, TypedDict

try:
    import fcntl

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

from backend.utils.common import format_error_msg

logger = logging.getLogger(__name__)

# [KO] 사용자별 최대 보관 검색 기록 수 기본값 (디스크 공간 제약 방어)
# [EN] Default maximum number of search history entries to keep per user (bounds disk footprint)
DEFAULT_MAX_HISTORY_ENTRIES = 1000

# [KO] 공유 히스토리 파일 전체 최대 보관 기록 수 (전체 용량 고갈 방지)
# [EN] Global maximum number of records across all users in a shared history file
DEFAULT_GLOBAL_MAX_ENTRIES_MULTIPLIER = 5

# [KO] 프로세스 간 락 획득 재시도 최대 대기 시간(초) / 재시도 간격(초)
# [EN] Max wait seconds and retry interval for cross-process lock acquisition
_FLOCK_TIMEOUT_SECONDS = 5.0
_FLOCK_RETRY_INTERVAL_SECONDS = 0.05


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

    보안 주의사항:
    - user_id=None 으로 사용하면 파일에 저장된 모든 사용자의 기록이 노출됩니다.
      공유 파일을 사용하는 멀티유저 환경에서는 반드시 user_id를 지정하세요.
    - storage_path는 신뢰 가능한 디렉터리 아래에 위치해야 합니다.
      암묵적 신뢰 기준 자체가 심볼릭 링크를 거치면 보안상 거부됩니다.

    [EN] A class to persist and manage search history in a local JSON file.

    Security notes:
    - Using user_id=None exposes all users' records stored in the file.
      Always specify user_id in multi-user environments sharing a file.
    - storage_path should reside within a trusted directory.
      An inferred trust root that resolves through a symlink is rejected.
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
        trusted_base_dir: Optional[str] = None,
    ):
        """
        [KO]
        히스토리 저장 경로를 설정하고 기존 데이터를 로드합니다.

        Args:
            storage_path: 히스토리를 저장할 JSON 파일 경로
            max_history_entries: 보관할 최대 검색 기록 수 (양의 정수여야 함)
            user_id: 특정 사용자에 한정하여 격리 관리할 사용자 식별자 (선택 사항).
                     None으로 사용 시 파일 내 모든 레코드가 노출될 수 있으므로
                     멀티유저 환경에서는 반드시 지정하세요.
            trusted_base_dir: 허용할 심볼릭 링크 대상 및 저장 경로의 기준 디렉터리 (절대 경로).
                              None이면 storage_path의 상위 디렉터리 경로를 검증하여 사용합니다.

        [EN]
        Sets the history storage path and loads existing data.

        Args:
            storage_path: JSON file path to store history
            max_history_entries: Maximum number of search history entries to keep.
                                 Must be a positive integer (not float or zero).
            user_id: Optional user identifier to partition/isolate history records.
                     When None, all records in the file are visible — specify in multi-user setups.
            trusted_base_dir: Absolute path that symlink targets and storage must reside within.
        """
        if not isinstance(max_history_entries, int) or isinstance(
            max_history_entries, bool
        ):
            raise TypeError(
                f"max_history_entries must be a plain int, got {type(max_history_entries).__name__}"
            )
        if max_history_entries <= 0:
            raise ValueError(
                f"max_history_entries must be a positive integer, got {max_history_entries}"
            )

        if user_id is None:
            logger.warning(
                "SearchHistory initialized without user_id: all records in the file are "
                "accessible. Set user_id to isolate records in multi-user environments.",
                extra={"action": "init_no_user_id"},
            )

        self.storage_path = storage_path
        self.max_history_entries = max_history_entries
        self.user_id = user_id

        # Comment 1: trusted_base_dir 처리 및 상위 심볼릭 링크 탈출 원천 차단
        abs_path = os.path.abspath(storage_path)
        raw_dir = os.path.dirname(abs_path) or "."
        if trusted_base_dir is not None:
            self._trusted_base_dir: str = os.path.abspath(trusted_base_dir)
            self._trusted_base_is_explicit = True
        else:
            # trusted_base_dir 미지정 시: storage_path의 상위 경로 중
            # 심볼릭 링크가 존재하면 신뢰 경계를 벗어날 위험이 있으므로 엄격히 검증
            self._trusted_base_dir = os.path.abspath(raw_dir)
            self._trusted_base_is_explicit = False

        self.history: Dict[str, Dict] = {}
        # Comment 9: 초기화(로드) 시에는 읽기 모드로 락 획득 (fcntl 없어도 초기화 허용)
        try:
            with self._interprocess_lock(write=False):
                self._load_history(persist_pruning=HAS_FCNTL)
        except PermissionError:
            # 잘못된 경로인 경우 빈 히스토리 유지
            self.history = {}

    def _validate_and_resolve_storage_path(self) -> str:
        """
        [KO] 저장 경로의 심볼릭 링크 및 상위 경로를 검증하고 안전한 대상 경로를 반환합니다.
             경로 상의 임의의 컴포넌트가 _trusted_base_dir 외부를 가리키면 PermissionError를 발생시킵니다.
        [EN] Validates storage_path and all parent components against _trusted_base_dir.
             Rejects symlinks pointing outside _trusted_base_dir.
        """
        abs_path = os.path.abspath(self.storage_path)
        trusted_dir = os.path.realpath(self._trusted_base_dir)

        # An inferred trust root must not resolve through a symlink, or the
        # symlink target would accidentally become its own trust boundary.
        if not self._trusted_base_is_explicit and trusted_dir != self._trusted_base_dir:
            raise PermissionError(
                "Inferred storage trust root resolves through a symlink"
            )

        # Comment 1: storage_path의 모든 상위 디렉터리 컴포넌트 순회 검증
        current = abs_path
        parts = []
        while True:
            parent = os.path.dirname(current)
            if parent == current:
                parts.append(current)
                break
            parts.append(current)
            current = parent

        # 상위 디렉터리들이 실제로 존재하는 경우 심볼릭 링크 및 탈출 여부 확인
        for part in reversed(parts):
            if os.path.islink(part):
                resolved_part = os.path.realpath(part)
                try:
                    common = os.path.commonpath([trusted_dir, resolved_part])
                    if common != trusted_dir and resolved_part != trusted_dir:
                        raise PermissionError(
                            f"보안 경고: 신뢰 범위를 벗어난 심볼릭 링크 거부: {part} -> {resolved_part}"
                        )
                except ValueError:
                    raise PermissionError(
                        f"보안 경고: 신뢰할 수 없는 경로를 가리키는 심볼릭 링크 거부: {part}"
                    )

        real_path = os.path.realpath(abs_path)
        real_parent = os.path.realpath(os.path.dirname(abs_path) or ".")

        try:
            common_parent = os.path.commonpath([trusted_dir, real_parent])
            if common_parent != trusted_dir and real_parent != trusted_dir:
                raise PermissionError(
                    f"보안 경고: 부모 디렉터리가 신뢰 범위 외부를 가리킵니다: {self.storage_path}"
                )
        except ValueError:
            raise PermissionError(
                f"보안 경고: 부모 디렉터리가 신뢰 범위 외부를 가리킵니다: {self.storage_path}"
            )

        if os.path.islink(abs_path):
            try:
                common = os.path.commonpath([trusted_dir, real_path])
                if common != trusted_dir and real_path != trusted_dir:
                    raise PermissionError(
                        f"보안 경고: 신뢰할 수 없는 디렉토리를 가리키는 심볼릭 링크 거부: {self.storage_path}"
                    )
            except ValueError:
                raise PermissionError(
                    f"보안 경고: 신뢰할 수 없는 경로를 가리키는 심볼릭 링크 거부: {self.storage_path}"
                )

        return real_path

    @contextmanager
    def _interprocess_lock(self, write: bool = False) -> Generator[None, None, None]:
        """
        [KO] 프로세스 간(fcntl.flock) 및 스레드 간(_lock) 배타적 잠금을 제공하는 컨텍스트 매니저.
             Comment 9: write=True일 때 fcntl이 없으면 RuntimeError 발생 (Fail-closed).
             write=False(읽기/초기화)일 때는 fcntl이 없어도 스레드 락으로 동기화 허용.
             Comment 3: 경로 검증 실패 시 거부된 경로에 락 파일을 생성하지 않고 즉시 예외 전파.
        [EN] Context manager for cross-process (fcntl.flock) and cross-thread (_lock) sync.
             Fails closed on write if fcntl is missing, but permits read-only operations.
             Aborts without creating lock files on rejected paths.
        """
        with SearchHistory._lock:
            # Comment 9: 쓰기 작업 시 fcntl 없으면 fail-closed
            if write and not HAS_FCNTL:
                raise RuntimeError(
                    "fcntl을 사용할 수 없는 플랫폼에서는 SearchHistory 쓰기 연산이 허용되지 않습니다. "
                    "데이터 무결성을 위해 fcntl 지원 플랫폼(Linux/macOS)에서 실행하세요."
                )

            # fcntl이 없는 환경의 읽기 작업은 스레드 락으로만 보호하고 통과
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

            # Comment 3: 경로 검증이 실패하면 절대 락 파일을 생성하지 않고 즉시 예외 전파
            target_path = self._validate_and_resolve_storage_path()

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
                raise RuntimeError(f"락 파일 생성 실패로 연산을 중단합니다: {e}") from e

            try:
                deadline = time.monotonic() + _FLOCK_TIMEOUT_SECONDS
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError as lock_err:
                        if lock_err.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                            raise
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                f"프로세스 간 락 획득 타임아웃 "
                                f"({_FLOCK_TIMEOUT_SECONDS}초): {lock_path}"
                            ) from lock_err
                        time.sleep(_FLOCK_RETRY_INTERVAL_SECONDS)

                SearchHistory._lock_depth.depth = 1
                try:
                    yield
                finally:
                    SearchHistory._lock_depth.depth = 0
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _refresh_history(self, persist_pruning: bool = True) -> bool:
        """
        [KO] 디스크에서 최신 히스토리를 읽어와 메모리를 동기화합니다. (락 내부에서 호출)
             파일이 없으면 self.history를 {}로 초기화합니다.
        [EN] Refreshes in-memory history from disk. (Must be called under lock)
             Clears self.history to {} when the file is absent (no stale data).
        """
        try:
            target_path = self._validate_and_resolve_storage_path()
        except PermissionError as e:
            logger.error(
                "저장 경로 검증 실패",
                extra={
                    "action": "refresh_path_validation",
                    "error_type": type(e).__name__,
                },
            )
            self.history = {}
            return False

        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    logger.warning(
                        "히스토리 파일 형식 오류: dict가 아닌 타입이 로드됨. 빈 히스토리로 초기화합니다.",
                        extra={
                            "action": "refresh_history_type_error",
                            "loaded_type": type(loaded).__name__,
                        },
                    )
                    self.history = {}
                    return True

                # Comment 8: dict가 아닌 레코드(None, int, str 등)는 필터링
                sanitized_loaded = {
                    sid: info
                    for sid, info in loaded.items()
                    if self._is_valid_record(info)
                }
                records_filtered = len(sanitized_loaded) != len(loaded)
                self.history = sanitized_loaded
                pruned = self._prune_history()
                # Comment 6: 프루닝 후 저장 실패 시 False 반환
                if (pruned or records_filtered) and persist_pruning:
                    if not self._save_history():
                        logger.error("프루닝된 히스토리 디스크 동기화 실패")
                        return False
                return True
            except (OSError, ValueError) as e:
                logger.error(
                    f"히스토리 갱신 실패: {type(e).__name__}: {format_error_msg(e)}",
                    extra={
                        "action": "refresh_history",
                        "error_type": type(e).__name__,
                    },
                )
                self.history = {}
                return False
        else:
            self.history = {}
            return True

    def _prune_history(self) -> bool:
        """
        [KO] 최대 보관 수를 초과할 경우 오래된 검색 기록을 정리합니다.
             user_id가 설정된 경우 해당 사용자의 기록을 max_history_entries 이하로 프루닝합니다.
             Comment 7: 다중 사용자로 인해 공유 파일 전체 크기가 과도하게 커지는 것을 방지하기 위해
             전체 레코드 수가 global 상한을 초과할 경우 오래된 항목부터 프루닝합니다.
             Comment 8: info가 dict가 아닌 레코드는 안전하게 무시합니다.
        [EN] Prunes older search records when exceeding maximum entries.
             When user_id is set, prunes records belonging to that user.
             Also bounds total shared history to prevent disk exhaustion.
             Returns True if any records were actually pruned.
        """
        pruned_any = False

        # 1. Comment 8: 유효한 dict 레코드만 분리
        valid_history = {
            sid: info for sid, info in self.history.items() if isinstance(info, dict)
        }
        if len(valid_history) != len(self.history):
            self.history = valid_history
            pruned_any = True

        # 2. 사용자별 프루닝 (user_id 설정 시)
        if self.user_id is not None:
            user_records = {
                sid: info
                for sid, info in self.history.items()
                if info.get("user_id") == self.user_id
            }
            other_records = {
                sid: info
                for sid, info in self.history.items()
                if info.get("user_id") != self.user_id
            }
            if len(user_records) > self.max_history_entries:
                sorted_user = sorted(
                    user_records.items(),
                    key=lambda x: str(x[1].get("search_time", "")),
                    reverse=True,
                )
                pruned_user = dict(sorted_user[: self.max_history_entries])
                self.history = {**other_records, **pruned_user}
                pruned_any = True

            # Comment 7: 전체 공유 파일 크기 상한 강제
            global_max = (
                self.max_history_entries * DEFAULT_GLOBAL_MAX_ENTRIES_MULTIPLIER
            )
            if len(self.history) > global_max:
                sorted_all = sorted(
                    self.history.items(),
                    key=lambda x: str(x[1].get("search_time", "")),
                    reverse=True,
                )
                self.history = dict(sorted_all[:global_max])
                pruned_any = True

            return pruned_any
        else:
            # user_id 미설정 시: 전체 히스토리 기준 프루닝
            if len(self.history) > self.max_history_entries:
                sorted_items = sorted(
                    self.history.items(),
                    key=lambda x: str(x[1].get("search_time", "")),
                    reverse=True,
                )
                self.history = dict(sorted_items[: self.max_history_entries])
                return True
            return pruned_any

    def _load_history(self, persist_pruning: bool = True) -> None:
        """
        [KO] 지정된 경로에서 저장된 검색 히스토리를 로드합니다.
        [EN] Loads saved search history from the specified path.
        """
        try:
            target_path = self._validate_and_resolve_storage_path()
        except PermissionError as e:
            logger.error(
                "보안 오류로 히스토리 로드 실패",
                extra={
                    "action": "load_path_validation",
                    "error_type": type(e).__name__,
                },
            )
            self.history = {}
            return

        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    logger.warning(
                        "히스토리 파일 형식 오류: dict가 아닌 타입. 빈 히스토리로 초기화합니다.",
                        extra={
                            "action": "load_history_type_error",
                            "loaded_type": type(loaded).__name__,
                        },
                    )
                    self.history = {}
                    return

                # Comment 8: dict가 아닌 레코드 필터링
                sanitized_loaded = {
                    sid: info
                    for sid, info in loaded.items()
                    if self._is_valid_record(info)
                }
                records_filtered = len(sanitized_loaded) != len(loaded)
                self.history = sanitized_loaded
                pruned = self._prune_history()
                # Comment 6: 로드 시 프루닝 발생 시 디스크 반영 및 실패 시 안전 처리
                if (pruned or records_filtered) and persist_pruning:
                    if not self._save_history():
                        logger.warning(
                            "로드 중 프루닝된 히스토리 저장 실패. 빈 상태로 초기화합니다."
                        )
                        self.history = {}
            except (OSError, ValueError) as e:
                logger.warning(
                    f"히스토리 로드 실패: {type(e).__name__}: {format_error_msg(e)}",
                    extra={
                        "action": "load_history",
                        "error_type": type(e).__name__,
                    },
                )
                self.history = {}
        else:
            storage_dir = os.path.dirname(target_path) or "."
            if persist_pruning and storage_dir != ".":
                try:
                    os.makedirs(storage_dir, exist_ok=True)
                except OSError:
                    pass
            self.history = {}

    @staticmethod
    def _is_valid_record(info: Any) -> bool:
        """Validate persisted fields that public methods consume."""
        if not isinstance(info, dict) or not isinstance(info.get("query"), str):
            return False

        results_count = info.get("results_count")
        if (
            not isinstance(results_count, int)
            or isinstance(results_count, bool)
            or results_count < 0
        ):
            return False

        top_results = info.get("top_results", [])
        if not isinstance(top_results, list) or any(
            not isinstance(result, str) for result in top_results
        ):
            return False

        for key in ("search_time", "created_at", "user_id"):
            value = info.get(key)
            if value is not None and not isinstance(value, str):
                return False
        return True

    def _save_history(self) -> bool:
        """
        [KO]
        메모리의 히스토리 데이터를 JSON 파일에 안전하게 저장합니다.
        원자적 교체, 소유자 전용 권한 강제(0o600), fsync, 임시 파일 정리를 보장합니다.
        Comment 5: 디렉터리 동기화 실패 시 에러를 전파하고 False를 반환합니다.

        Returns:
            저장 성공 시 True, 직렬화 또는 I/O 실패 시 False
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
                    "error_type": type(e).__name__,
                },
            )
            return False

        # 2단계: 대상 경로 해석 및 검증
        try:
            target_path = self._validate_and_resolve_storage_path()
        except PermissionError as e:
            logger.error(
                "보안 오류로 저장 실패",
                extra={
                    "action": "save_path_validation",
                    "error_type": type(e).__name__,
                },
            )
            return False

        storage_dir = os.path.dirname(target_path) or "."

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
                tmp_f.flush()
                os.fsync(tmp_f.fileno())

            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass

            os.replace(tmp_path, target_path)

            # Comment 5 & 10: 디렉터리 메타데이터 fsync 실패 시 에러 처리
            dir_fd = -1
            try:
                dir_fd = os.open(storage_dir, os.O_RDONLY)
                os.fsync(dir_fd)
            except OSError as dir_err:
                logger.error(
                    "디렉터리 fsync 실패로 저장이 불완전합니다.",
                    extra={
                        "action": "save_history_dir_fsync",
                        "error_type": type(dir_err).__name__,
                    },
                )
                return False
            finally:
                if dir_fd >= 0:
                    try:
                        os.close(dir_fd)
                    except OSError:
                        pass

            return True

        except (OSError, UnicodeEncodeError) as e:
            logger.error(
                f"히스토리 저장 실패: {type(e).__name__}: {format_error_msg(e)}",
                extra={
                    "action": "save_history_write",
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
        락 획득(write=True) → 디스크 최신 상태 동기화 → 스냅샷 캡처 → 뮤테이션 → 저장 → 실패 시 원복을 수행합니다.
        Comment 10: 락 타임아웃(TimeoutError) 발생 시 예외를 던지지 않고 False를 반환합니다.
        """
        try:
            with self._interprocess_lock(write=True):
                # 1. 디스크 최신 상태와 동기화
                if not self._refresh_history(persist_pruning=True):
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
                    logger.error(
                        "히스토리 변경 적용 실패",
                        extra={"action": action, "error_type": type(e).__name__},
                    )
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
        except (TimeoutError, PermissionError, RuntimeError) as e:
            logger.error(
                "영속화 중 락 또는 권한 오류 발생",
                extra={"action": action, "error_type": type(e).__name__},
            )
            return False

    def add_search(
        self, query: str, results_count: int, top_results: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        [KO] 새로운 검색 기록을 추가하고 영속화합니다. 실패 시 None을 반환합니다.
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
        Comment 4: _refresh_history() 실패 시 None 반환.
        """
        try:
            with self._interprocess_lock(write=False):
                if not self._refresh_history(persist_pruning=HAS_FCNTL):
                    return None
                record = self.history.get(search_id)
                if (
                    record
                    and self.user_id is not None
                    and record.get("user_id") != self.user_id
                ):
                    return None
                return record
        except (PermissionError, RuntimeError, TimeoutError):
            return None

    def get_recent_searches(self, limit: int = 10) -> List[Dict]:
        """
        [KO] 최근 수행된 검색 기록들을 최신순으로 정렬하여 조회합니다.
        Comment 4: _refresh_history() 실패 시 빈 리스트 반환.
        """
        try:
            with self._interprocess_lock(write=False):
                if not self._refresh_history(persist_pruning=HAS_FCNTL):
                    return []
                user_items = [
                    (sid, info)
                    for sid, info in self.history.items()
                    if isinstance(info, dict)
                    and (self.user_id is None or info.get("user_id") == self.user_id)
                ]
                sorted_history = sorted(
                    user_items,
                    key=lambda x: str(x[1].get("search_time", "")),
                    reverse=True,
                )
                return [{"id": sid, **info} for sid, info in sorted_history[:limit]]
        except (PermissionError, RuntimeError, TimeoutError):
            return []

    def get_all_searches(self) -> Dict[str, Dict]:
        """
        [KO] 저장된 모든 검색 기록을 조회합니다. 사용자 ID가 설정된 경우 격리 조회합니다.
        Comment 4: _refresh_history() 실패 시 빈 딕셔너리 반환.
        """
        try:
            with self._interprocess_lock(write=False):
                if not self._refresh_history(persist_pruning=HAS_FCNTL):
                    return {}
                if self.user_id is None:
                    return {
                        sid: info
                        for sid, info in self.history.items()
                        if isinstance(info, dict)
                    }
                return {
                    sid: info
                    for sid, info in self.history.items()
                    if isinstance(info, dict) and info.get("user_id") == self.user_id
                }
        except (PermissionError, RuntimeError, TimeoutError):
            return {}

    def delete_search(self, search_id: str) -> bool:
        """
        [KO] 특정 검색 ID의 기록을 삭제합니다.
        """
        try:
            with self._interprocess_lock(write=False):
                if not self._refresh_history(persist_pruning=HAS_FCNTL):
                    return False
                if search_id not in self.history:
                    return False
                record = self.history[search_id]
                if (
                    self.user_id is not None
                    and isinstance(record, dict)
                    and record.get("user_id") != self.user_id
                ):
                    return False

            return self._apply_and_persist(
                mutate=lambda: self.history.pop(search_id, None),
                rollback=lambda: self.history.update({search_id: record}),
                rollback_msg="히스토리 저장 실패로 검색 기록 삭제가 취소되었습니다.",
                action="delete_search_rollback",
            )
        except (PermissionError, RuntimeError, TimeoutError):
            return False

    def clear_all(self) -> bool:
        """
        [KO] 검색 기록을 삭제합니다. user_id 설정 시 해당 사용자의 기록만 삭제합니다.
        """

        def _mutate() -> None:
            if self.user_id is None:
                self.history.clear()
            else:
                self.history = {
                    k: v
                    for k, v in self.history.items()
                    if isinstance(v, dict) and v.get("user_id") != self.user_id
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
        Comment 4: _refresh_history() 실패 시 기본 통계 반환.
        """
        default_stats: SearchStatistics = {
            "total_searches": 0,
            "avg_results": 0.0,
            "most_common_query": None,
        }
        try:
            with self._interprocess_lock(write=False):
                if not self._refresh_history(persist_pruning=HAS_FCNTL):
                    return default_stats
                user_records = [
                    h
                    for h in self.history.values()
                    if isinstance(h, dict)
                    and (self.user_id is None or h.get("user_id") == self.user_id)
                ]
                if not user_records:
                    return default_stats

                total_searches = len(user_records)
                avg_results = (
                    sum(h.get("results_count", 0) for h in user_records)
                    / total_searches
                )
                query_counts = Counter(h.get("query", "") for h in user_records)
                top_queries = query_counts.most_common(1)
                most_common = top_queries[0][0] if top_queries else None

                return {
                    "total_searches": total_searches,
                    "avg_results": round(avg_results, 1),
                    "most_common_query": most_common,
                }
        except (PermissionError, RuntimeError, TimeoutError):
            return default_stats

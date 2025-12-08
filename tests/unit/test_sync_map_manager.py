# tests/unit/test_sync_map_manager.py

"""
SyncMapManager Unit Tests

매핑 CRUD 동작 및 Thread Safety를 검증합니다.
"""

import pytest
from typing import Callable, Dict, List, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, wait, ALL_COMPLETED, Future

from backend.mcp.sync_map_manager import SyncMapManager
from backend.models.external_sync import ExternalToolType


# Note: Fixtures는 tests/conftest.py에서 제공됨


# ==========================================
# Test: CRUD Operations
# ==========================================


def test_sync_map_manager_create_and_retrieve(map_manager: SyncMapManager):
    """
    [Unit] SyncMapManager: 매핑 생성 및 조회

    검증:
    - update_mapping으로 새 매핑 생성
    - get_mapping_by_internal_id로 조회
    - get_mapping_by_external_path로 조회 (O(1))
    """
    # Arrange & Act
    mapping = map_manager.update_mapping(
        internal_id="test_123",
        external_path="/vault/test.md",
        tool_type=ExternalToolType.OBSIDIAN,
        current_hash="abc123",
    )

    # Assert
    assert mapping.internal_file_id == "test_123"
    assert mapping.external_path == "/vault/test.md"
    assert mapping.last_synced_hash == "abc123"

    # 조회 검증
    retrieved_by_id = map_manager.get_mapping_by_internal_id("test_123")
    assert retrieved_by_id is not None
    assert retrieved_by_id.external_path == "/vault/test.md"

    retrieved_by_path = map_manager.get_mapping_by_external_path("/vault/test.md")
    assert retrieved_by_path is not None
    assert retrieved_by_path.internal_file_id == "test_123"


def test_sync_map_manager_update_existing(map_manager: SyncMapManager):
    """
    [Unit] SyncMapManager: 기존 매핑 업데이트

    검증:
    - 동일 internal_id로 update_mapping 재호출
    - external_path 변경 반영
    - 인덱스 업데이트 확인
    """
    # Arrange
    map_manager.update_mapping(
        internal_id="update_test",
        external_path="/vault/old_path.md",
        tool_type=ExternalToolType.OBSIDIAN,
    )

    # Act
    updated = map_manager.update_mapping(
        internal_id="update_test",
        external_path="/vault/new_path.md",
        tool_type=ExternalToolType.OBSIDIAN,
        current_hash="new_hash",
    )

    # Assert
    assert updated.external_path == "/vault/new_path.md"
    assert updated.last_synced_hash == "new_hash"

    # 이전 경로로 조회 시 None
    old_path_result = map_manager.get_mapping_by_external_path("/vault/old_path.md")
    assert old_path_result is None

    # 새 경로로 조회 성공
    new_path_result = map_manager.get_mapping_by_external_path("/vault/new_path.md")
    assert new_path_result is not None
    assert new_path_result.internal_file_id == "update_test"


def test_sync_map_manager_remove(map_manager: SyncMapManager):
    """
    [Unit] SyncMapManager: 매핑 삭제

    검증:
    - remove_mapping으로 삭제
    - 조회 시 None 반환
    - 인덱스에서도 제거 확인
    """
    # Arrange
    map_manager.update_mapping(
        internal_id="remove_test",
        external_path="/vault/remove.md",
        tool_type=ExternalToolType.OBSIDIAN,
    )

    # Act
    result = map_manager.remove_mapping("remove_test")

    # Assert
    assert result is True

    # 조회 시 None
    assert map_manager.get_mapping_by_internal_id("remove_test") is None
    assert map_manager.get_mapping_by_external_path("/vault/remove.md") is None

    # 존재하지 않는 ID 삭제 시 False
    result_nonexistent = map_manager.remove_mapping("nonexistent")
    assert result_nonexistent is False


def test_sync_map_manager_get_total_count(map_manager: SyncMapManager):
    """
    [Unit] SyncMapManager: 전체 매핑 개수 조회

    검증:
    - get_total_count() 정확성
    - 매핑 추가/삭제 시 개수 변화
    """
    # Arrange
    assert map_manager.get_total_count() == 0

    # Act: 매핑 추가
    map_manager.update_mapping(
        internal_id="count_test_1",
        external_path="/vault/count1.md",
        tool_type=ExternalToolType.OBSIDIAN,
    )
    map_manager.update_mapping(
        internal_id="count_test_2",
        external_path="/vault/count2.md",
        tool_type=ExternalToolType.OBSIDIAN,
    )

    # Assert
    assert map_manager.get_total_count() == 2

    # Act: 매핑 삭제
    map_manager.remove_mapping("count_test_1")

    # Assert
    assert map_manager.get_total_count() == 1


# ==========================================
# Test: Thread Safety (Concurrency)
# ==========================================


def _submit_workers(
    executor: ThreadPoolExecutor, num_workers: int, worker_func: Callable[[int], None]
) -> Tuple[List[Future[None]], Dict[Future[None], int]]:
    """
    Helper: Worker 제출 및 Future-Worker 매핑 생성

    Args:
        executor: ThreadPoolExecutor 인스턴스
        num_workers: Worker 개수
        worker_func: Worker 함수 (worker_idx: int를 인자로 받고 None 반환)

    Returns:
        tuple: (futures 리스트, future_to_worker 딕셔너리)
            - futures: Future[None] 객체 리스트
            - future_to_worker: Future를 worker_idx로 매핑하는 딕셔너리
    """
    future_to_worker: Dict[Future[None], int] = {
        executor.submit(worker_func, idx): idx for idx in range(num_workers)
    }
    futures: List[Future[None]] = list(future_to_worker.keys())
    return futures, future_to_worker


def test_sync_map_manager_thread_safe_concurrent_access(map_manager: SyncMapManager):
    """
    [Concurrency] SyncMapManager: 동시 업데이트 및 조회 시 스레드 세이프 동작

    검증:
    - 여러 스레드에서 동시에 update_mapping 호출
    - 동시에 get_mapping_by_internal_id / get_mapping_by_external_path 호출
    - 예외 없이 일관된 매핑 조회
    - 레이스 컨디션 없음
    - Timeout으로 교착 상태 방지
    """
    num_workers = 8
    iterations_per_worker = 50
    internal_id_prefix = "concurrent-internal"
    external_path_prefix = "/concurrent/external"

    def worker(worker_idx: int) -> None:
        for i in range(iterations_per_worker):
            internal_id = f"{internal_id_prefix}-{worker_idx}-{i}"
            external_path = f"{external_path_prefix}/{worker_idx}/{i}.md"

            # 동시 업데이트
            mapping = map_manager.update_mapping(
                internal_id=internal_id,
                external_path=external_path,
                tool_type=ExternalToolType.OBSIDIAN,
                current_hash=f"hash-{worker_idx}-{i}",
            )

            # 내부 ID 기준 조회
            by_internal = map_manager.get_mapping_by_internal_id(internal_id)
            assert by_internal is not None, f"매핑 조회 실패: {internal_id}"
            assert by_internal.internal_file_id == mapping.internal_file_id
            assert by_internal.external_path == mapping.external_path

            # 외부 path 기준 조회 (O(1) 인덱스 사용)
            by_external = map_manager.get_mapping_by_external_path(external_path)
            assert by_external is not None, f"경로 조회 실패: {external_path}"
            assert by_external.internal_file_id == mapping.internal_file_id
            assert by_external.external_path == mapping.external_path

    # Act: 멀티스레드 실행 (ALL_COMPLETED로 모든 worker 완료 대기)
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Helper 함수로 Future-Worker 매핑 생성
        futures, future_to_worker = _submit_workers(executor, num_workers, worker)

        done, not_done = wait(
            futures,
            timeout=10,  # 10초 timeout (교착 상태 방지)
            return_when=ALL_COMPLETED,  # 모든 worker 완료 대기
        )

    # Assert: 모든 worker가 완료되었는지 확인
    assert (
        len(done) == num_workers
    ), f"모든 worker가 완료되어야 함. 완료: {len(done)}, 미완료: {len(not_done)}"

    # Assert: 예외 없이 완료 (worker_idx로 식별, 불변 조건 강제)
    for f in done:
        try:
            worker_idx = future_to_worker[f]
        except KeyError as e:
            raise AssertionError(
                f"Future {f}에 대한 worker_idx 매핑을 찾을 수 없습니다. "
                f"이는 내부 불변 조건 위반입니다."
            ) from e

        exc = f.exception()
        assert exc is None, f"worker {worker_idx}에서 예외 발생: {exc!r}"

    # 최종 매핑 개수 검증
    expected_count = num_workers * iterations_per_worker
    assert (
        map_manager.get_total_count() == expected_count
    ), f"예상 매핑 개수: {expected_count}, 실제: {map_manager.get_total_count()}"


def test_sync_map_manager_concurrent_update_same_id(map_manager: SyncMapManager):
    """
    [Concurrency] SyncMapManager: 동일 ID에 대한 동시 업데이트

    검증:
    - 여러 스레드가 동일 internal_id를 동시에 업데이트
    - 레이스 컨디션 없이 최종 일관성 유지
    - 인덱스 정합성 확인
    - Timeout으로 교착 상태 방지
    """
    num_workers = 10
    shared_internal_id = "shared-id"

    def worker(worker_idx: int) -> None:
        external_path = f"/shared/path-{worker_idx}.md"
        map_manager.update_mapping(
            internal_id=shared_internal_id,
            external_path=external_path,
            tool_type=ExternalToolType.OBSIDIAN,
            current_hash=f"hash-{worker_idx}",
        )

    # Act: 동일 ID에 대한 동시 업데이트 (ALL_COMPLETED)
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Helper 함수로 Future-Worker 매핑 생성
        futures, future_to_worker = _submit_workers(executor, num_workers, worker)

        done, not_done = wait(
            futures,
            timeout=10,
            return_when=ALL_COMPLETED,
        )

    # Assert: 모든 worker 완료
    assert (
        len(done) == num_workers
    ), f"모든 worker가 완료되어야 함. 완료: {len(done)}, 미완료: {len(not_done)}"

    # Assert: 예외 없이 완료 (worker_idx로 식별, 불변 조건 강제)
    for f in done:
        try:
            worker_idx = future_to_worker[f]
        except KeyError as e:
            raise AssertionError(
                f"Future {f}에 대한 worker_idx 매핑을 찾을 수 없습니다. "
                f"이는 내부 불변 조건 위반입니다."
            ) from e

        exc = f.exception()
        assert exc is None, f"worker {worker_idx}에서 예외 발생: {exc!r}"

    # 최종 상태 확인: 하나의 매핑만 존재해야 함
    mapping = map_manager.get_mapping_by_internal_id(shared_internal_id)
    assert mapping is not None
    assert mapping.internal_file_id == shared_internal_id

    # 인덱스 일관성: 최종 external_path로 조회 가능
    by_path = map_manager.get_mapping_by_external_path(mapping.external_path)
    assert by_path is not None
    assert by_path.internal_file_id == shared_internal_id

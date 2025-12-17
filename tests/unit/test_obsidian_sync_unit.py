# tests/unit/test_obsidian_sync_unit.py

"""
Obsidian 동기화 Unit Tests

개별 컴포넌트의 독립적인 동작을 검증합니다.
"""

import pytest
from pathlib import Path

from backend.mcp.obsidian_server import ObsidianSyncService, ObsidianFileWatcher
from backend.models.conflict import (
    SyncConflict,
    SyncConflictType,
    ResolutionStatus,
)
from backend.models.external_sync import ExternalToolType


# Note: Fixtures는 tests/conftest.py에서 제공됩니다.


# ==========================================
# Test: 해시 계산 및 충돌 감지
# ==========================================


def test_file_hash_calculation_consistency(sync_service: ObsidianSyncService):
    """
    [Unit] 파일 해시 계산 일관성 검증

    시나리오:
    1. 동일 내용에 대해 해시 계산
    2. 해시 값 일관성 확인
    3. 내용 변경 시 해시 변경 확인
    """
    # Arrange
    original_content = "# Original\n\nOriginal content."
    modified_content = "# Modified\n\nModified content."

    # Act
    hash1 = sync_service.calculate_file_hash(original_content)
    hash2 = sync_service.calculate_file_hash(original_content)  # 동일 내용
    hash3 = sync_service.calculate_file_hash(modified_content)

    # Assert
    assert hash1 == hash2, "동일 내용은 동일 해시를 생성해야 함"
    assert hash1 != hash3, "내용 변경 시 해시가 달라야 함"


def test_conflict_detection_by_hash(sync_service: ObsidianSyncService):
    """
    [Unit] 해시 기반 충돌 감지 로직 검증

    시나리오:
    1. 해시 불일치 시 변경 감지
    2. 해시 일치 시 변경 없음
    3. last_synced_hash가 None인 경우 처리
    """
    # Arrange
    current_hash = "abc123"
    last_synced_hash = "def456"

    # Act & Assert
    assert (
        sync_service.detect_conflict_by_hash(current_hash, last_synced_hash) is True
    ), "해시 불일치 시 변경 감지되어야 함"

    assert (
        sync_service.detect_conflict_by_hash(current_hash, current_hash) is False
    ), "해시 일치 시 변경 없음"

    assert (
        sync_service.detect_conflict_by_hash(current_hash, None) is True
    ), "last_synced_hash가 None이면 변경으로 간주"


# ==========================================
# Test: FileWatcher 이벤트 핸들링
# ==========================================


def test_file_watcher_event_handling(mock_vault: Path):
    """
    [Unit] FileWatcher 이벤트 핸들링 검증

    시나리오:
    1. 각 이벤트 타입별 콜백 호출 확인
    2. .md 파일만 필터링 확인
    3. 디렉토리 이벤트 무시 확인
    """
    # Arrange
    events_captured = []

    def mock_callback(file_path: str, event_type: str):
        events_captured.append((file_path, event_type))

    watcher = ObsidianFileWatcher(mock_callback)

    # Mock events
    class MockEvent:
        def __init__(
            self, src_path: str, is_directory: bool = False, dest_path: str = None
        ):
            self.src_path = src_path
            self.is_directory = is_directory
            self.dest_path = dest_path

    # Act: 다양한 이벤트 시뮬레이션
    watcher.on_created(MockEvent(str(mock_vault / "created.md")))
    watcher.on_modified(MockEvent(str(mock_vault / "modified.md")))
    watcher.on_deleted(MockEvent(str(mock_vault / "deleted.md")))
    watcher.on_moved(
        MockEvent(str(mock_vault / "old.md"), dest_path=str(mock_vault / "new.md"))
    )

    # 무시되어야 하는 이벤트
    watcher.on_created(MockEvent(str(mock_vault / "ignored.txt")))  # .md 아님
    watcher.on_created(
        MockEvent(str(mock_vault / "dir"), is_directory=True)
    )  # 디렉토리

    # Assert
    assert len(events_captured) == 4, "4개의 .md 파일 이벤트만 캡처되어야 함"
    assert events_captured[0][1] == "created"
    assert events_captured[1][1] == "modified"
    assert events_captured[2][1] == "deleted"
    assert events_captured[3][1] == "moved"


# ==========================================
# Test: SyncConflict 모델
# ==========================================


def test_conflict_model_creation():
    """
    [Unit] SyncConflict 모델 생성 및 속성 검증

    시나리오:
    1. Content Mismatch 충돌 생성
    2. 필수 속성 확인
    3. 기본 상태 확인
    """
    # Arrange & Act
    conflict = SyncConflict(
        file_id="test_file_123",
        external_path="/vault/test.md",
        tool_type=ExternalToolType.OBSIDIAN,
        conflict_type=SyncConflictType.CONTENT_MISMATCH,
        local_hash="abc123",
        remote_hash="def456",
    )

    # Assert
    assert conflict.conflict_type == SyncConflictType.CONTENT_MISMATCH
    assert conflict.local_hash != conflict.remote_hash
    assert conflict.status == ResolutionStatus.PENDING
    assert conflict.file_id == "test_file_123"
    assert conflict.tool_type == ExternalToolType.OBSIDIAN

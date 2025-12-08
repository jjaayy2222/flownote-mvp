# tests/integration/test_obsidian_sync.py

"""
Obsidian 동기화 통합 테스트

파일 생성/수정/삭제 시나리오 및 충돌 해결 전략을 검증합니다.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from backend.mcp.obsidian_server import ObsidianSyncService, ObsidianFileWatcher
from backend.mcp.sync_map_manager import SyncMapManager
from backend.services.conflict_resolution_service import ConflictResolutionService
from backend.config.mcp_config import ObsidianConfig
from backend.models.external_sync import ExternalToolType, ExternalFileMapping
from backend.models.conflict import (
    SyncConflict,
    SyncConflictType,
    ResolutionStrategy,
    ResolutionMethod,
    ResolutionStatus,
)


# ==========================================
# Fixtures
# ==========================================


@pytest.fixture
def mock_vault(tmp_path: Path) -> Path:
    """임시 Obsidian Vault 디렉토리 생성"""
    vault = tmp_path / "test_vault"
    vault.mkdir()
    return vault


@pytest.fixture
def obsidian_config(mock_vault: Path) -> ObsidianConfig:
    """테스트용 Obsidian 설정"""
    return ObsidianConfig(vault_path=str(mock_vault), sync_interval=300, enabled=True)


@pytest.fixture
def sync_service(obsidian_config: ObsidianConfig) -> ObsidianSyncService:
    """ObsidianSyncService 인스턴스"""
    return ObsidianSyncService(obsidian_config)


@pytest.fixture
def map_manager(tmp_path: Path) -> SyncMapManager:
    """SyncMapManager 인스턴스 (임시 저장소)"""
    return SyncMapManager(storage_dir=str(tmp_path / "mcp"))


# ==========================================
# Test: 파일 생성 동기화
# ==========================================


@pytest.mark.asyncio
async def test_file_creation_sync(
    sync_service: ObsidianSyncService, map_manager: SyncMapManager, mock_vault: Path
):
    """
    [Integration] 파일 생성 동기화 검증

    시나리오:
    1. Vault에 새 .md 파일 생성
    2. sync_all() 호출
    3. 매핑 정보 생성 확인
    """
    # Arrange
    test_file = mock_vault / "test_note.md"
    test_content = "# Test Note\n\nThis is a test."
    test_file.write_text(test_content, encoding="utf-8")

    # Act
    conflicts = await sync_service.sync_all()

    # Assert
    assert len(conflicts) == 0, "새 파일 생성 시 충돌 없어야 함"

    # Note: MVP에서는 sync_all()이 스캔만 하고 매핑을 자동 생성하지 않음
    # 실제 매핑 생성은 별도 로직 필요 (TODO)


@pytest.mark.asyncio
async def test_file_modification_detection(
    sync_service: ObsidianSyncService, mock_vault: Path
):
    """
    [Integration] 파일 수정 감지 검증

    시나리오:
    1. 기존 파일 내용 변경
    2. 해시 계산 및 비교
    3. 변경 감지 확인
    """
    # Arrange
    test_file = mock_vault / "existing_note.md"
    original_content = "# Original\n\nOriginal content."
    modified_content = "# Modified\n\nModified content."

    test_file.write_text(original_content, encoding="utf-8")
    original_hash = sync_service.calculate_file_hash(original_content)

    # Act
    test_file.write_text(modified_content, encoding="utf-8")
    modified_hash = sync_service.calculate_file_hash(modified_content)

    # Assert
    assert original_hash != modified_hash, "내용 변경 시 해시가 달라야 함"

    # 충돌 감지 로직 검증
    is_changed = sync_service.detect_conflict_by_hash(modified_hash, original_hash)
    assert is_changed is True, "해시 불일치 시 변경 감지되어야 함"


@pytest.mark.asyncio
async def test_file_deletion_event(sync_service: ObsidianSyncService, mock_vault: Path):
    """
    [Integration] 파일 삭제 이벤트 처리 검증

    시나리오:
    1. FileWatcher 콜백 설정
    2. 파일 삭제 시뮬레이션
    3. on_deleted 이벤트 확인
    """
    # Arrange
    events_captured = []

    def mock_callback(file_path: str, event_type: str):
        events_captured.append((file_path, event_type))

    watcher = ObsidianFileWatcher(mock_callback)

    # Act: Mock event 생성
    class MockDeleteEvent:
        is_directory = False
        src_path = str(mock_vault / "deleted_note.md")

    watcher.on_deleted(MockDeleteEvent())

    # Assert
    assert len(events_captured) == 1, "삭제 이벤트 1회 캡처되어야 함"
    assert events_captured[0][1] == "deleted", "이벤트 타입이 'deleted'여야 함"


# ==========================================
# Test: 충돌 시나리오
# ==========================================


@pytest.mark.asyncio
async def test_conflict_detection_content_mismatch():
    """
    [Integration] Content Mismatch 충돌 감지

    시나리오:
    1. 로컬/원격 해시 불일치
    2. SyncConflict 생성
    3. conflict_type 검증
    """
    # Arrange
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


@pytest.mark.asyncio
async def test_conflict_resolution_remote_wins(
    sync_service: ObsidianSyncService, map_manager: SyncMapManager, mock_vault: Path
):
    """
    [Integration] 충돌 해결: Remote Wins 전략

    시나리오:
    1. Content Mismatch 충돌 생성
    2. AUTO_BY_CONTEXT 전략 적용
    3. 원격 내용으로 덮어쓰기 시도 (NotImplementedError 예상)
    """
    # Arrange
    test_file = mock_vault / "conflict_test.md"
    remote_content = "# Remote Version\n\nRemote content wins."
    test_file.write_text(remote_content, encoding="utf-8")

    conflict = SyncConflict(
        file_id="conflict_123",
        external_path=str(test_file),
        tool_type=ExternalToolType.OBSIDIAN,
        conflict_type=SyncConflictType.CONTENT_MISMATCH,
        local_hash="local_hash",
        remote_hash="remote_hash",
    )

    strategy = ResolutionStrategy(
        method=ResolutionMethod.AUTO_BY_CONTEXT,
        recommended_value=None,
        confidence=0.9,
        reasoning="Remote wins strategy",
        conflict_id=conflict.conflict_id,
    )

    resolution_service = ConflictResolutionService(sync_service, map_manager)

    # Act
    resolution = await resolution_service.resolve_conflict(conflict, strategy)

    # Assert
    assert (
        resolution.status == ResolutionStatus.FAILED
    ), "MVP에서는 File Service 미구현으로 실패"
    assert (
        "not implemented" in resolution.notes.lower()
    ), "NotImplementedError 메시지 포함"


@pytest.mark.asyncio
async def test_conflict_resolution_manual_not_implemented(
    sync_service: ObsidianSyncService, map_manager: SyncMapManager
):
    """
    [Integration] 충돌 해결: MANUAL_OVERRIDE 미구현 처리

    시나리오:
    1. MANUAL_OVERRIDE 전략 호출
    2. NotImplementedError 발생 확인
    3. ConflictResolution.status=FAILED 확인
    """
    # Arrange
    conflict = SyncConflict(
        file_id="manual_test",
        external_path="/vault/manual.md",
        tool_type=ExternalToolType.OBSIDIAN,
        conflict_type=SyncConflictType.CONTENT_MISMATCH,
        local_hash="hash1",
        remote_hash="hash2",
    )

    strategy = ResolutionStrategy(
        method=ResolutionMethod.MANUAL_OVERRIDE,
        recommended_value="User selected content",
        confidence=1.0,
        reasoning="Manual selection",
        conflict_id=conflict.conflict_id,
    )

    resolution_service = ConflictResolutionService(sync_service, map_manager)

    # Act
    resolution = await resolution_service.resolve_conflict(conflict, strategy)

    # Assert
    assert resolution.status == ResolutionStatus.FAILED
    assert "Manual conflict resolution requires File Service" in resolution.notes


# ==========================================
# Test: SyncMapManager CRUD
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

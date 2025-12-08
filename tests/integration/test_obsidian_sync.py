# tests/integration/test_obsidian_sync.py

"""
Obsidian 동기화 통합 테스트

파일 생성/수정/삭제 시나리오 및 충돌 해결 전략을 검증합니다.
"""

import pytest
from pathlib import Path

from backend.mcp.obsidian_server import ObsidianSyncService, ObsidianFileWatcher
from backend.mcp.sync_map_manager import SyncMapManager
from backend.services.conflict_resolution_service import ConflictResolutionService
from backend.config.mcp_config import ObsidianConfig
from backend.models.external_sync import ExternalToolType
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
# Test: 파일 동기화 기본 시나리오
# ==========================================


@pytest.mark.asyncio
async def test_file_creation_no_conflict(
    sync_service: ObsidianSyncService, mock_vault: Path
):
    """
    [Integration] 새 파일 생성 시 sync_all()이 예외/충돌 없이 동작하는지 검증

    현재 MVP 구현에서는 sync_all()이 Vault를 스캔하고 충돌 정보를 반환하지만,
    매핑 생성/검증은 아직 포함되지 않습니다.

    시나리오:
    1. Vault에 새 .md 파일 생성
    2. sync_all() 호출
    3. 반환된 충돌 목록이 비어 있는지 확인

    TODO:
    - SyncMapManager를 통해 실제 파일 발견/매핑 생성이 이루어졌는지까지 검증하는
      통합 테스트를 추가하거나, 이 테스트를 확장합니다.
    """
    # Arrange: Vault에 새 노트 생성
    test_file = mock_vault / "test_note.md"
    test_content = "# Test Note\n\nThis is a test."
    test_file.write_text(test_content, encoding="utf-8")

    # Act: 동기화 실행
    conflicts = await sync_service.sync_all()

    # Assert: 새 파일 생성 시 충돌이 없어야 한다
    assert len(conflicts) == 0, "새 파일 생성 시 sync_all()은 충돌을 반환하지 않아야 함"


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
# Test: 충돌 시나리오
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


@pytest.mark.asyncio
async def test_conflict_resolution_remote_wins_status(
    sync_service: ObsidianSyncService, map_manager: SyncMapManager, mock_vault: Path
):
    """
    [Integration] 충돌 해결: Remote Wins 전략 (상태 검증)

    시나리오:
    1. Content Mismatch 충돌 생성
    2. AUTO_BY_CONTEXT 전략 적용
    3. ResolutionStatus.FAILED 확인 (MVP: File Service 미구현)

    Note: 에러 메시지 문자열 대신 상태 Enum으로 검증하여 안정성 확보
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

    # Assert: 상태 Enum으로 검증 (문자열 대신)
    assert (
        resolution.status == ResolutionStatus.FAILED
    ), "MVP에서는 File Service 미구현으로 FAILED 상태여야 함"
    assert resolution.conflict_id == conflict.conflict_id
    assert resolution.resolved_by == "system"


@pytest.mark.asyncio
async def test_conflict_resolution_manual_not_implemented_status(
    sync_service: ObsidianSyncService, map_manager: SyncMapManager
):
    """
    [Integration] 충돌 해결: MANUAL_OVERRIDE 미구현 처리 (상태 검증)

    시나리오:
    1. MANUAL_OVERRIDE 전략 호출
    2. ResolutionStatus.FAILED 확인
    3. NotImplementedError 처리 확인

    Note: 상태 Enum으로 검증하여 에러 메시지 변경에 강건함
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

    # Assert: 상태 Enum으로 검증
    assert resolution.status == ResolutionStatus.FAILED
    assert (
        "not implemented" in resolution.notes.lower()
    ), "NotImplementedError 관련 메시지 포함 (보조 검증)"

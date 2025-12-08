# tests/integration/test_obsidian_sync.py

"""
Obsidian 동기화 통합 테스트

End-to-End 시나리오 및 서비스 간 상호작용을 검증합니다.
"""

import pytest
from pathlib import Path

from backend.mcp.obsidian_server import ObsidianSyncService
from backend.mcp.sync_map_manager import SyncMapManager
from backend.services.conflict_resolution_service import ConflictResolutionService
from backend.models.external_sync import ExternalToolType
from backend.models.conflict import (
    SyncConflict,
    SyncConflictType,
    ResolutionStrategy,
    ResolutionMethod,
    ResolutionStatus,
)


# Note: Fixtures는 tests/conftest.py에서 제공됩니다.


# ==========================================
# Test: End-to-End 동기화 시나리오
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


# ==========================================
# Test: 충돌 해결 통합 시나리오
# ==========================================


@pytest.mark.asyncio
async def test_conflict_resolution_remote_wins_integration(
    sync_service: ObsidianSyncService, map_manager: SyncMapManager, mock_vault: Path
):
    """
    [Integration] 충돌 해결: Remote Wins 전략 (End-to-End)

    시나리오:
    1. Vault에 파일 생성
    2. Content Mismatch 충돌 생성
    3. ConflictResolutionService를 통한 해결 시도
    4. ResolutionStatus.FAILED 확인 (MVP: File Service 미구현)

    Note: 서비스 간 상호작용 및 전체 플로우 검증
    """
    # Arrange: Vault에 파일 생성
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

    # Act: 충돌 해결 시도
    resolution = await resolution_service.resolve_conflict(conflict, strategy)

    # Assert: 상태 Enum으로 검증
    assert (
        resolution.status == ResolutionStatus.FAILED
    ), "MVP에서는 File Service 미구현으로 FAILED 상태여야 함"
    assert resolution.conflict_id == conflict.conflict_id
    assert resolution.resolved_by == "system"
    assert resolution.resolved_at is not None


@pytest.mark.asyncio
async def test_conflict_resolution_manual_not_implemented_integration(
    sync_service: ObsidianSyncService, map_manager: SyncMapManager
):
    """
    [Integration] 충돌 해결: MANUAL_OVERRIDE 미구현 처리 (End-to-End)

    시나리오:
    1. MANUAL_OVERRIDE 전략으로 충돌 해결 시도
    2. ConflictResolutionService가 NotImplementedError 처리
    3. ResolutionStatus.FAILED 및 적절한 메시지 확인

    Note: 예외 처리 및 서비스 응답 검증
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
    ), "NotImplementedError 관련 메시지 포함"
    assert resolution.resolved_at is not None

# tests/integration/test_phase5_sync_flow.py

"""
Phase 5 통합 테스트: Obsidian 동기화 전체 플로우

Step 5 요구사항:
1. Obsidian에서 파일 생성 -> FlowNote가 분류 후 이동
2. Conflict 감지 및 Rename 전략 적용
3. MCP Tools 호출 검증
"""

import pytest
import asyncio
from pathlib import Path
from datetime import datetime

from backend.services.obsidian_sync import ObsidianSyncService
from backend.services.conflict_resolution_service import ConflictResolutionService
from backend.services.sync_service import SyncServiceBase
from backend.models.external_sync import (
    ExternalToolConnection,
    ExternalToolType,
    ConnectionConfig,
)
from backend.models.conflict import (
    SyncConflict,
    SyncConflictType,
    ResolutionStrategy,
    ResolutionMethod,
    ResolutionStatus,
)


# ==========================================
# Test: Obsidian 파일 생성 -> 분류 -> 이동
# ==========================================


@pytest.mark.asyncio
async def test_obsidian_file_creation_and_classification(mock_vault: Path):
    """
    [Integration] Obsidian에서 파일 생성 시 FlowNote가 분류하고 PARA 폴더로 이동

    시나리오:
    1. Obsidian Vault에 새 파일 생성
    2. ObsidianSyncService를 통해 파일 읽기
    3. PARA 카테고리로 분류 (Projects)
    4. move_file_to_para로 파일 이동
    5. 이동된 파일 확인
    """
    # Arrange: Vault에 Projects 폴더 생성
    projects_dir = mock_vault / "Projects"
    projects_dir.mkdir(exist_ok=True)

    # 테스트 파일 생성 (Vault 루트)
    test_file = mock_vault / "new_project_idea.md"
    test_content = """# New Project Idea

This is a new project about building an AI assistant.
Deadline: Next month.
"""
    test_file.write_text(test_content, encoding="utf-8")

    # ObsidianSyncService 초기화
    conn = ExternalToolConnection(
        tool_type=ExternalToolType.OBSIDIAN,
        config=ConnectionConfig(base_path=str(mock_vault), enabled=True),
    )
    sync_service = ObsidianSyncService(conn)

    # Act: 파일 읽기
    content = await sync_service.pull_file(str(test_file))
    assert content == test_content, "파일 내용이 정확히 읽혀야 함"

    # Act: PARA 폴더로 이동 (Projects)
    new_path = await sync_service.move_file_to_para(str(test_file), "Projects")

    # Assert: 파일이 이동되었는지 확인
    assert new_path is not None, "파일 이동이 성공해야 함"
    assert Path(new_path).exists(), "이동된 파일이 존재해야 함"
    assert Path(new_path).parent == projects_dir, "Projects 폴더로 이동되어야 함"
    assert not test_file.exists(), "원본 파일은 삭제되어야 함"


# ==========================================
# Test: Conflict 감지 및 Rename 전략
# ==========================================


@pytest.mark.asyncio
async def test_conflict_detection_and_rename_resolution(mock_vault: Path, map_manager):
    """
    [Integration] 3-way 충돌 감지 및 Rename 전략 적용

    시나리오:
    1. 로컬과 원격 모두 수정된 파일 생성
    2. detect_conflict_3way로 충돌 감지
    3. ConflictResolutionService로 Rename 전략 적용
    4. 백업 파일 생성 확인
    5. 원본 파일에 원격 내용 적용 확인
    """
    # Arrange: 충돌 파일 생성
    conflict_file = mock_vault / "conflict_note.md"
    local_content = "# Local Version\n\nLocal changes here."
    remote_content = "# Remote Version\n\nRemote changes here."

    # 로컬 파일 생성
    conflict_file.write_text(local_content, encoding="utf-8")

    # ObsidianSyncService 초기화
    conn = ExternalToolConnection(
        tool_type=ExternalToolType.OBSIDIAN,
        config=ConnectionConfig(base_path=str(mock_vault), enabled=True),
    )
    sync_service = ObsidianSyncService(conn)

    # 해시 계산
    local_hash = sync_service.calculate_file_hash(local_content)
    remote_hash = sync_service.calculate_file_hash(remote_content)
    last_synced_hash = "different_hash"  # 양쪽 모두 변경됨

    # Act: 충돌 감지
    # 원격 파일 생성 (별도 경로)
    remote_file = mock_vault / ".remote" / "conflict_note.md"
    remote_file.parent.mkdir(exist_ok=True)
    remote_file.write_text(remote_content, encoding="utf-8")

    conflict = sync_service.detect_conflict_3way(
        file_id=str(conflict_file),
        external_path=str(remote_file),
        local_hash=local_hash,
        remote_hash=remote_hash,
        last_synced_hash=last_synced_hash,
    )

    # Assert: 충돌이 감지되어야 함
    assert conflict is not None, "양쪽 모두 변경 시 충돌이 감지되어야 함"
    assert isinstance(conflict, SyncConflict), "SyncConflict 객체가 반환되어야 함"
    assert conflict.conflict_type == SyncConflictType.CONTENT_MISMATCH

    # Act: Rename 전략으로 해결
    resolution_service = ConflictResolutionService(sync_service, map_manager)
    strategy = ResolutionStrategy(
        method=ResolutionMethod.AUTO_BY_CONFIDENCE,
        recommended_value=None,
        confidence=0.9,
        reasoning="Rename strategy for conflict resolution",
        conflict_id=conflict.conflict_id,
    )

    resolution = await resolution_service.resolve_conflict(conflict, strategy)

    # Assert: 해결 상태 확인
    assert resolution.status == ResolutionStatus.RESOLVED, "충돌 해결이 성공해야 함"
    assert resolution.conflict_id == conflict.conflict_id, "충돌 ID가 일치해야 함"

    # Assert: 백업 파일 생성 확인
    backup_files = list(mock_vault.glob("conflict_note_conflict_*.md"))
    assert len(backup_files) >= 1, "백업 파일이 최소 1개 생성되어야 함"

    # 백업 파일 이름 검증
    backup_file = backup_files[0]
    assert backup_file.name.startswith(
        "conflict_note_conflict_"
    ), "백업 파일 이름 형식 확인"
    assert backup_file.suffix == ".md", "백업 파일 확장자 확인"

    # Assert: 백업 파일 내용 확인 (로컬 내용 보존)
    backup_content = backup_file.read_text(encoding="utf-8")
    assert backup_content == local_content, "백업 파일에 로컬 내용이 보존되어야 함"

    # Assert: 원본 파일 내용 확인 (원격 내용 적용)
    final_content = conflict_file.read_text(encoding="utf-8")
    assert final_content == remote_content, "원본 파일에 원격 내용이 적용되어야 함"


# ==========================================
# Test: 충돌 없는 동기화
# ==========================================


@pytest.mark.asyncio
async def test_no_conflict_when_only_local_changed(mock_vault: Path):
    """
    [Integration] 로컬만 변경 시 충돌이 발생하지 않음

    시나리오:
    1. 로컬만 수정된 파일
    2. detect_conflict_3way 호출
    3. None 반환 확인 (충돌 없음)
    """
    # Arrange
    test_file = mock_vault / "local_only_change.md"
    test_file.write_text("# Local Change", encoding="utf-8")

    conn = ExternalToolConnection(
        tool_type=ExternalToolType.OBSIDIAN,
        config=ConnectionConfig(base_path=str(mock_vault), enabled=True),
    )
    sync_service = ObsidianSyncService(conn)

    local_hash = sync_service.calculate_file_hash("# Local Change")
    remote_hash = "same_as_last_synced"
    last_synced_hash = "same_as_last_synced"

    # Act
    conflict = sync_service.detect_conflict_3way(
        file_id=str(test_file),
        external_path=str(test_file),
        local_hash=local_hash,
        remote_hash=remote_hash,
        last_synced_hash=last_synced_hash,
    )

    # Assert
    assert conflict is None, "로컬만 변경 시 충돌이 없어야 함"


@pytest.mark.asyncio
async def test_no_conflict_when_only_remote_changed(mock_vault: Path):
    """
    [Integration] 원격만 변경 시 충돌이 발생하지 않음

    시나리오:
    1. 원격만 수정된 파일
    2. detect_conflict_3way 호출
    3. None 반환 확인 (충돌 없음)
    """
    # Arrange
    test_file = mock_vault / "remote_only_change.md"
    test_file.write_text("# Remote Change", encoding="utf-8")

    conn = ExternalToolConnection(
        tool_type=ExternalToolType.OBSIDIAN,
        config=ConnectionConfig(base_path=str(mock_vault), enabled=True),
    )
    sync_service = ObsidianSyncService(conn)

    local_hash = "same_as_last_synced"
    remote_hash = sync_service.calculate_file_hash("# Remote Change")
    last_synced_hash = "same_as_last_synced"

    # Act
    conflict = sync_service.detect_conflict_3way(
        file_id=str(test_file),
        external_path=str(test_file),
        local_hash=local_hash,
        remote_hash=remote_hash,
        last_synced_hash=last_synced_hash,
    )

    # Assert
    assert conflict is None, "원격만 변경 시 충돌이 없어야 함"


# ==========================================
# Test: MCP Tools 호출 검증
# ==========================================


# ==========================================
# Test: MCP Tools 호출 검증
# ==========================================


@pytest.mark.asyncio
async def test_mcp_tools_integration(mock_vault: Path):
    """
    [Integration] MCP Tools 호출 검증

    시나리오:
    1. MCP 서버의 classify_content 도구 시뮬레이션
    2. 테스트 텍스트 분류
    3. 결과 검증

    Note: 이 테스트는 MCP 도구 통합 경로를 검증합니다.
    실제 MCP 서버 호출은 E2E 테스트에서 수행됩니다.
    """
    from unittest.mock import patch, AsyncMock

    # Arrange: 분류할 텍스트 준비
    test_text = "오늘 프로젝트 회의가 있습니다. 마감일은 다음주입니다."

    # MCP 도구 호출 시뮬레이션
    # 실제 구현에서는 backend.mcp.server의 classify_content를 호출
    from backend.services.classification_service import ClassificationService

    service = ClassificationService()

    # Act: 분류 실행
    # 실제 API 호출 방지를 위해 HybridClassifier.classify를 Mocking
    with patch(
        "backend.classifier.hybrid_classifier.HybridClassifier.classify",
        new_callable=AsyncMock,
    ) as mock_hybrid:
        mock_hybrid.return_value = {
            "category": "Projects",
            "confidence": 0.85,
            "reasoning": "Mocked PARA result",
            "snapshot_id": "mock_snapshot_123",
        }

        result = await service.classify(
            text=test_text, file_id="test_mcp_001", user_id="test_user"
        )

    # Assert: 분류 결과 검증
    assert result is not None, "분류 결과가 반환되어야 함"
    assert result.category in [
        "Projects",
        "Areas",
        "Resources",
        "Archive",
    ], "유효한 PARA 카테고리가 반환되어야 함"
    assert 0.0 <= result.confidence <= 1.0, "신뢰도가 0-1 범위여야 함"
    assert result.reasoning is not None, "분류 이유가 제공되어야 함"

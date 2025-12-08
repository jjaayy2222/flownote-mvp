# tests/conftest.py

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil
import os
import sys

# 프로젝트 루트를 Python Path에 추가
sys.path.append(str(Path(__file__).parent.parent))

# 테스트 환경 변수 설정
os.environ["TESTING"] = "true"
os.environ["GPT4O_MINI_API_KEY"] = "test-key"  # Mocking용

from backend.main import app
from backend.services.onboarding_service import OnboardingService
from backend.services.classification_service import ClassificationService
from backend.data_manager import DataManager


@pytest.fixture(scope="session")
def test_data_dir():
    """테스트용 임시 데이터 디렉토리 생성 및 정리"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def client():
    """FastAPI TestClient"""
    return TestClient(app)


@pytest.fixture
def onboarding_service():
    return OnboardingService()


@pytest.fixture
def classification_service():
    return ClassificationService()


@pytest.fixture
def sample_user():
    return {
        "user_id": "test_user_123",
        "occupation": "소프트웨어 엔지니어",
        "areas": ["백엔드", "AI"],
        "interests": ["Python", "FastAPI"],
    }


@pytest.fixture
def sample_text():
    return "오늘 프로젝트 회의가 있습니다. 마감일은 다음주입니다."


# ==========================================
# Obsidian Sync Fixtures (Phase 3)
# ==========================================


@pytest.fixture
def mock_vault(tmp_path: Path) -> Path:
    """임시 Obsidian Vault 디렉토리 생성"""
    vault = tmp_path / "test_vault"
    vault.mkdir()
    return vault


@pytest.fixture
def obsidian_config(mock_vault: Path):
    """테스트용 Obsidian 설정"""
    from backend.config.mcp_config import ObsidianConfig

    return ObsidianConfig(vault_path=str(mock_vault), sync_interval=300, enabled=True)


@pytest.fixture
def sync_service(obsidian_config):
    """ObsidianSyncService 인스턴스"""
    from backend.mcp.obsidian_server import ObsidianSyncService

    return ObsidianSyncService(obsidian_config)


@pytest.fixture
def map_manager(tmp_path: Path):
    """SyncMapManager 인스턴스 (임시 저장소)"""
    from backend.mcp.sync_map_manager import SyncMapManager

    return SyncMapManager(storage_dir=str(tmp_path / "mcp"))

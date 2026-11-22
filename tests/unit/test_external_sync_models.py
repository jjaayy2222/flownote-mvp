# tests/unit/test_external_sync_models.py

"""
[KO] backend/models/external_sync.py Pydantic 모델 단위 테스트.
[EN] Unit tests for Pydantic models in backend/models/external_sync.py.

테스트 범위:
- Pydantic V2 ConfigDict 마이그레이션 검증 (class Config 제거 및 격리 프로세스/인스턴스화 시 DeprecationWarning 미발생)
- ExternalToolConnection schema_extra 예시 내 PII 비포함 및 범용 경로 검증
- ConnectionConfig 기본값 및 선택 필드 검증
- ExternalToolConnection 인스턴스화, 직렬화(model_dump), 역직렬화(model_validate) 검증
- ExternalFileMapping 및 ExternalSyncLog default_factory 실시간 호출 및 고유 타임스탬프 검증 (Controlled clock)
- Enum 타입 정합성 및 직렬화 검증
"""

import os
import subprocess
import sys
import warnings
from datetime import datetime
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from pydantic.warnings import PydanticDeprecatedSince20

from backend.models.external_sync import (
    ConnectionConfig,
    ExternalFileMapping,
    ExternalSyncLog,
    ExternalToolConnection,
    ExternalToolType,
    SyncStatus,
)


class TestExternalSyncModelsConfigDict:
    """Pydantic V2 ConfigDict 마이그레이션 및 스키마 검증"""

    def test_no_pydantic_deprecated_warnings_on_clean_import(self):
        """Comment 1: reload 없이 신규 프로세스 격리 환경에서 모듈 임포트 시 PydanticDeprecatedSince20 경고가 발생하지 않는지 검증합니다."""
        env = os.environ.copy()
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        env["PYTHONPATH"] = repo_root

        script = (
            "import warnings; "
            "from pydantic.warnings import PydanticDeprecatedSince20; "
            "warnings.simplefilter('error', PydanticDeprecatedSince20); "
            "import backend.models.external_sync"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
        )
        assert (
            result.returncode == 0
        ), f"임포트 중 PydanticDeprecatedSince20 경고 발생: {result.stderr}"

    def test_no_pydantic_deprecated_warnings_on_instantiation(self):
        """인스턴스화 시 PydanticDeprecatedSince20 경고가 발생하지 않는지 검증합니다."""
        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")

            conn = ExternalToolConnection(
                tool_type=ExternalToolType.OBSIDIAN,
                config=ConnectionConfig(base_path="/path/to/vault"),
            )
            assert conn.tool_type == ExternalToolType.OBSIDIAN

            deprecated_warnings = [
                w
                for w in recorded_warnings
                if issubclass(w.category, PydanticDeprecatedSince20)
            ]
            assert not deprecated_warnings

    def test_model_config_is_config_dict(self):
        """ExternalToolConnection의 model_config가 ConfigDict 규격을 만족하는지 검증합니다."""
        config = ExternalToolConnection.model_config
        assert isinstance(config, dict)
        assert "json_schema_extra" in config

    def test_json_schema_extra_contains_no_pii(self):
        """json_schema_extra 예시가 범용 경로이며 개인 홈 디렉터리 패턴이 없는지 검증합니다."""
        schema_extra = ExternalToolConnection.model_config.get("json_schema_extra")
        assert isinstance(schema_extra, dict)
        example = schema_extra.get("example")
        assert isinstance(example, dict)
        config_example = example.get("config")
        assert isinstance(config_example, dict)
        base_path = config_example.get("base_path", "")

        assert base_path == "/path/to/vault"
        assert not str(base_path).startswith(("/Users/", "/home/", "C:\\Users"))


class TestConnectionConfig:
    """ConnectionConfig 모델 단위 테스트"""

    def test_default_values(self):
        """기본값(sync_interval=300, enabled=True)이 올바르게 초기화되는지 검증합니다."""
        cfg = ConnectionConfig()
        assert cfg.base_path is None
        assert cfg.api_key is None
        assert cfg.sync_interval == 300
        assert cfg.enabled is True

    def test_custom_values(self):
        """사용자 정의 설정값이 올바르게 할당되는지 검증합니다."""
        cfg = ConnectionConfig(
            base_path="/custom/vault",
            api_key="secret-token",
            sync_interval=60,
            enabled=False,
        )
        assert cfg.base_path == "/custom/vault"
        assert cfg.api_key == "secret-token"
        assert cfg.sync_interval == 60
        assert cfg.enabled is False


class TestExternalToolConnection:
    """ExternalToolConnection 모델 단위 테스트"""

    def test_valid_instantiation(self):
        """필수 필드 및 기본값(sync_status=IDLE)이 올바르게 생성되는지 검증합니다."""
        conn = ExternalToolConnection(
            tool_type=ExternalToolType.NOTION,
            config=ConnectionConfig(api_key="ntn_test_123"),
        )
        assert conn.tool_type == ExternalToolType.NOTION
        assert conn.tool_type.value == "notion"
        assert conn.sync_status == SyncStatus.IDLE
        assert conn.sync_status.value == "idle"
        assert conn.last_synced_at is None
        assert conn.error_message is None

    def test_missing_required_fields_raises_validation_error(self):
        """필수 필드 누락 시 ValidationError가 발생하는지 검증합니다."""
        with pytest.raises(ValidationError):
            ExternalToolConnection.model_validate({})

    def test_model_dump_and_validate_roundtrip(self):
        """model_dump 및 model_validate를 통한 직렬화/역직렬화 정합성을 검증합니다."""
        now = datetime.now()
        original = ExternalToolConnection(
            tool_type=ExternalToolType.GDRIVE,
            config=ConnectionConfig(enabled=True),
            last_synced_at=now,
            sync_status=SyncStatus.COMPLETED,
            error_message=None,
        )
        dumped = original.model_dump()
        reconstructed = ExternalToolConnection.model_validate(dumped)

        assert reconstructed.tool_type == ExternalToolType.GDRIVE
        assert reconstructed.sync_status == SyncStatus.COMPLETED
        assert reconstructed.last_synced_at == now


class TestExternalFileMapping:
    """ExternalFileMapping 모델 단위 테스트"""

    @patch("backend.models.external_sync._time_provider")
    def test_instantiation_calls_factory_per_instance(self, mock_time_provider):
        """Comment 2 & 3: 제어된 시계(controlled clock)를 사용하여 각 인스턴스마다 default_factory가 독립 호출되는지 엄밀하게 검증합니다."""
        t1 = datetime(2026, 11, 23, 10, 0, 0)
        t2 = datetime(2026, 11, 23, 10, 0, 1)
        mock_time_provider.side_effect = [t1, t2]

        mapping1 = ExternalFileMapping(
            internal_file_id="flownote_doc_001",
            external_path="/vault/notes/daily.md",
            tool_type=ExternalToolType.OBSIDIAN,
        )
        mapping2 = ExternalFileMapping(
            internal_file_id="flownote_doc_002",
            external_path="/vault/notes/weekly.md",
            tool_type=ExternalToolType.OBSIDIAN,
        )

        assert mapping1.internal_file_id == "flownote_doc_001"
        assert mapping1.external_path == "/vault/notes/daily.md"
        assert mapping1.tool_type == ExternalToolType.OBSIDIAN
        assert mapping1.last_synced_hash is None

        # 타임스탬프 재사용/고정값 방지 및 개별 팩토리 호출 검증
        assert mapping1.last_synced_at == t1
        assert mapping2.last_synced_at == t2
        assert mapping1.last_synced_at != mapping2.last_synced_at
        assert mock_time_provider.call_count == 2

    def test_custom_synced_hash_and_time(self):
        """해시 및 특정 시각이 올바르게 반영되는지 검증합니다."""
        fixed_time = datetime(2026, 11, 22, 10, 0, 0)
        mapping = ExternalFileMapping(
            internal_file_id="doc_002",
            external_path="notion_page_abc",
            tool_type=ExternalToolType.NOTION,
            last_synced_hash="sha256_mock_hash",
            last_synced_at=fixed_time,
        )
        assert mapping.last_synced_hash == "sha256_mock_hash"
        assert mapping.last_synced_at == fixed_time


class TestExternalSyncLog:
    """ExternalSyncLog 모델 단위 테스트"""

    @patch("backend.models.external_sync._time_provider")
    def test_instantiation_calls_factory_per_instance(self, mock_time_provider):
        """Comment 2 & 3: 제어된 시계(controlled clock)를 사용하여 각 인스턴스마다 고유한 timestamp가 실시간 생성되는지 검증합니다."""
        t1 = datetime(2026, 11, 23, 11, 0, 0)
        t2 = datetime(2026, 11, 23, 11, 0, 5)
        mock_time_provider.side_effect = [t1, t2]

        log1 = ExternalSyncLog(
            id="log_001",
            tool_type=ExternalToolType.OBSIDIAN,
            action="push",
            file_path="/notes/test1.md",
            status=SyncStatus.SYNCING,
            message="Pushing local changes",
            details={"chunks_count": 5},
        )
        log2 = ExternalSyncLog(
            id="log_002",
            tool_type=ExternalToolType.NOTION,
            action="pull",
            file_path="/notes/test2.md",
            status=SyncStatus.COMPLETED,
            message="Pulling remote changes",
        )

        assert log1.id == "log_001"
        assert log1.action == "push"
        assert log1.status == SyncStatus.SYNCING
        assert log1.details == {"chunks_count": 5}
        assert log1.timestamp == t1

        assert log2.id == "log_002"
        assert log2.action == "pull"
        assert log2.status == SyncStatus.COMPLETED
        assert log2.timestamp == t2

        # 고정값/재사용 방지 및 각 인스턴스별 독립 호출 검증
        assert log1.timestamp != log2.timestamp
        assert mock_time_provider.call_count == 2

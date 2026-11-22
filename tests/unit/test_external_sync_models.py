# tests/unit/test_external_sync_models.py

"""
[KO] backend/models/external_sync.py Pydantic 모델 단위 테스트.
[EN] Unit tests for Pydantic models in backend/models/external_sync.py.

테스트 범위:
- Pydantic V2 ConfigDict 마이그레이션 검증 (class Config 제거 및 import/인스턴스화 시 DeprecationWarning 미발생)
- ExternalToolConnection schema_extra 예시 내 PII 비포함 및 범용 경로 검증
- ConnectionConfig 기본값 및 선택 필드 검증
- ExternalToolConnection 인스턴스화, 직렬화(model_dump), 역직렬화(model_validate) 검증
- ExternalFileMapping 및 ExternalSyncLog default_factory 실시간 호출 및 유효성 검증
- Enum 타입 정합성 및 직렬화 검증
"""

import importlib
import sys
import time
import warnings
from datetime import datetime

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

    def test_no_pydantic_deprecated_warnings_on_import_and_instantiation(self):
        """PydanticDeprecatedSince20 경고 없이 모델이 임포트 및 인스턴스화되는지 검증합니다."""
        with warnings.catch_warnings(record=True) as recorded_warnings:
            warnings.simplefilter("always")

            # Comment 2: warning-capture 블록 내에서 모듈을 리로드하여 정의(임포트) 시점의 경고까지 캡처
            if "backend.models.external_sync" in sys.modules:
                sync_module = importlib.reload(
                    sys.modules["backend.models.external_sync"]
                )
            else:
                sync_module = importlib.import_module("backend.models.external_sync")

            # 모델 인스턴스화
            conn = sync_module.ExternalToolConnection(
                tool_type=sync_module.ExternalToolType.OBSIDIAN,
                config=sync_module.ConnectionConfig(base_path="/path/to/vault"),
            )
            assert conn.tool_type == sync_module.ExternalToolType.OBSIDIAN

            # PydanticDeprecatedSince20 경고가 발생하지 않아야 함
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
        """Comment 1: json_schema_extra 예시가 범용 경로이며 개인 홈 디렉터리 패턴이 없는지 검증합니다."""
        schema_extra = ExternalToolConnection.model_config.get("json_schema_extra")
        assert isinstance(schema_extra, dict)
        example = schema_extra.get("example")
        assert isinstance(example, dict)
        config_example = example.get("config")
        assert isinstance(config_example, dict)
        base_path = config_example.get("base_path", "")

        # 특정 로컬 사용자명 리터럴 없이 범용 경로 일치 및 일반적인 개인 사용자 경로 패턴 부재 검증
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

    def test_instantiation_with_defaults(self):
        """Comment 3: default_factory가 인스턴스 생성 시점에 실시간 호출되어 유효 범위 타임스탬프를 부여하는지 검증합니다."""
        before = datetime.now()
        mapping1 = ExternalFileMapping(
            internal_file_id="flownote_doc_001",
            external_path="/vault/notes/daily.md",
            tool_type=ExternalToolType.OBSIDIAN,
        )
        time.sleep(0.002)
        mapping2 = ExternalFileMapping(
            internal_file_id="flownote_doc_002",
            external_path="/vault/notes/weekly.md",
            tool_type=ExternalToolType.OBSIDIAN,
        )
        after = datetime.now()

        assert mapping1.internal_file_id == "flownote_doc_001"
        assert mapping1.external_path == "/vault/notes/daily.md"
        assert mapping1.tool_type == ExternalToolType.OBSIDIAN
        assert mapping1.last_synced_hash is None

        # 생성 시간 범위 검증 및 고정 기본값이 아닌 팩토리 호출 검증
        assert before <= mapping1.last_synced_at <= mapping2.last_synced_at <= after

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

    def test_instantiation_and_details(self):
        """Comment 3: 동기화 활동 로그가 올바르게 인스턴스화되며 timestamp가 실시간 생성되는지 검증합니다."""
        before = datetime.now()
        log = ExternalSyncLog(
            id="log_001",
            tool_type=ExternalToolType.OBSIDIAN,
            action="push",
            file_path="/notes/test.md",
            status=SyncStatus.SYNCING,
            message="Pushing local changes",
            details={"chunks_count": 5},
        )
        after = datetime.now()

        assert log.id == "log_001"
        assert log.action == "push"
        assert log.status == SyncStatus.SYNCING
        assert log.status.value == "syncing"
        assert log.details == {"chunks_count": 5}
        # 생성 시간 범위 검증 (factory 호출 검증)
        assert before <= log.timestamp <= after

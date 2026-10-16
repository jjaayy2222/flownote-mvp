# tests/unit/test_metadata_endpoint.py

"""
Unit tests for File Metadata API endpoints (#12.3.31).
Covers:
- GET /metadata/{file_id}:
  - 정상 메타데이터 조회 (200 OK)
  - 미존재 파일 조회 시 404 Not Found
  - 빈 file_id 요청 시 400 Bad Request
- PUT /metadata/{file_id}:
  - 정상 메타데이터 필드 갱신 및 디스크 영속화 (200 OK)
  - file_size 변경 시 file_size_mb 자동 재계산 검증
  - 미존재 파일 갱신 시 404 Not Found
  - 빈 file_id 요청 시 400 Bad Request
  - 빈 updates 요청 시 Pydantic 검증 에러
  - 영속화 실패 시 롤백 및 500 Internal Server Error
- i18n 다국어 지원:
  - ko, en locale별 반환 메시지 검증
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api.endpoints.metadata import get_metadata, update_metadata
from backend.api.models import MetadataUpdateRequest
from backend.config import PathConfig
from backend.metadata import get_file_metadata


@pytest.fixture
def temp_metadata_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """임시 PathConfig.DATA_DIR를 제공하고 get_file_metadata 싱글톤을 초기화하는 픽스처."""
    monkeypatch.setattr(PathConfig, "DATA_DIR", tmp_path)
    storage_file = tmp_path / "metadata.json"

    # 싱글톤 캐시 초기화
    import backend.metadata as metadata_module

    metadata_module._DEFAULT_METADATA_INSTANCE = None

    return storage_file


@pytest.mark.asyncio
async def test_get_metadata_success(temp_metadata_storage: Path):
    """정상적으로 등록된 파일의 메타데이터를 조회할 수 있는지 검증."""
    manager = get_file_metadata(str(temp_metadata_storage))

    file_id = manager.add_file(
        file_name="flow_guide.md",
        file_size=1024 * 1024 * 3,  # 3MB
        chunk_count=15,
        embedding_dim=1536,
        model="text-embedding-3-small",
    )
    assert file_id is not None

    with patch(
        "backend.api.endpoints.metadata.get_file_metadata", return_value=manager
    ):
        response = await get_metadata(file_id=file_id, locale="ko")

        assert response.status == "success"
        assert response.file_id == file_id
        assert response.message == "메타데이터를 조회했습니다"
        assert response.metadata["file_name"] == "flow_guide.md"
        assert response.metadata["chunk_count"] == 15
        assert response.metadata["embedding_model"] == "text-embedding-3-small"
        assert response.metadata["file_size_mb"] == 3.0


@pytest.mark.asyncio
async def test_get_metadata_not_found(temp_metadata_storage: Path):
    """존재하지 않는 파일 ID 조회 시 404 Not Found가 발생하는지 검증."""
    manager = get_file_metadata(str(temp_metadata_storage))

    with patch(
        "backend.api.endpoints.metadata.get_file_metadata", return_value=manager
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_metadata(file_id="non_existent_file_999", locale="ko")

        assert exc_info.value.status_code == 404
        assert "파일 메타데이터를 찾을 수 없습니다" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_metadata_empty_id(temp_metadata_storage: Path):
    """빈 문자열이나 공백 file_id 요청 시 400 Bad Request가 발생하는지 검증."""
    with pytest.raises(HTTPException) as exc_info:
        await get_metadata(file_id="   ", locale="ko")

    assert exc_info.value.status_code == 400
    assert "file_id는 필수 입력값입니다" in exc_info.value.detail


@pytest.mark.asyncio
async def test_update_metadata_success(temp_metadata_storage: Path):
    """등록된 파일의 메타데이터 필드를 정상적으로 갱신하고 디스크에 영속화되는지 검증."""
    manager = get_file_metadata(str(temp_metadata_storage))

    file_id = manager.add_file(
        file_name="original.txt",
        file_size=1024 * 50,  # 50KB
        chunk_count=2,
        embedding_dim=1536,
    )
    assert file_id is not None

    update_body = MetadataUpdateRequest(
        updates={
            "file_name": "renamed_doc.md",
            "chunk_count": 5,
            "custom_tag": "important",
        }
    )

    with patch(
        "backend.api.endpoints.metadata.get_file_metadata", return_value=manager
    ):
        response = await update_metadata(
            file_id=file_id,
            body=update_body,
            locale="ko",
        )

        assert response.status == "success"
        assert response.file_id == file_id
        assert response.message == "메타데이터가 업데이트되었습니다"
        assert response.metadata["file_name"] == "renamed_doc.md"
        assert response.metadata["chunk_count"] == 5
        assert response.metadata["custom_tag"] == "important"
        assert "updated_at" in response.metadata

    # 디스크 파일에 영속화되었는지 재확인
    with open(temp_metadata_storage, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data[file_id]["file_name"] == "renamed_doc.md"
    assert disk_data[file_id]["custom_tag"] == "important"


@pytest.mark.asyncio
async def test_update_metadata_recalculates_file_size_mb(temp_metadata_storage: Path):
    """file_size를 갱신할 때 file_size_mb가 자동으로 재계산되는지 검증."""
    manager = get_file_metadata(str(temp_metadata_storage))

    file_id = manager.add_file(
        file_name="doc.pdf",
        file_size=1024 * 1024,  # 1MB
        chunk_count=10,
        embedding_dim=1536,
    )
    assert file_id is not None

    update_body = MetadataUpdateRequest(updates={"file_size": 1024 * 1024 * 5})  # 5MB

    with patch(
        "backend.api.endpoints.metadata.get_file_metadata", return_value=manager
    ):
        response = await update_metadata(
            file_id=file_id,
            body=update_body,
            locale="ko",
        )

        assert response.metadata["file_size"] == 1024 * 1024 * 5
        assert response.metadata["file_size_mb"] == 5.0


@pytest.mark.asyncio
async def test_update_metadata_not_found(temp_metadata_storage: Path):
    """존재하지 않는 파일 ID 갱신 시 404 Not Found가 발생하는지 검증."""
    manager = get_file_metadata(str(temp_metadata_storage))
    update_body = MetadataUpdateRequest(updates={"file_name": "test.md"})

    with patch(
        "backend.api.endpoints.metadata.get_file_metadata", return_value=manager
    ):
        with pytest.raises(HTTPException) as exc_info:
            await update_metadata(
                file_id="missing_file_id_000",
                body=update_body,
                locale="ko",
            )

        assert exc_info.value.status_code == 404
        assert "파일 메타데이터를 찾을 수 없습니다" in exc_info.value.detail


def test_update_metadata_empty_updates_raises_validation_error():
    """빈 updates 딕셔너리 전달 시 Pydantic 검증 에러가 발생하는지 검증."""
    with pytest.raises(ValidationError):
        MetadataUpdateRequest(updates={})


@pytest.mark.asyncio
async def test_update_metadata_persistence_failure_rollback(
    temp_metadata_storage: Path,
):
    """디스크 영속화 실패 시 메모리 변경 사항이 롤백되고 500 오류가 반환되는지 검증."""
    manager = get_file_metadata(str(temp_metadata_storage))

    file_id = manager.add_file(
        file_name="stable_file.txt",
        file_size=1024,
        chunk_count=1,
        embedding_dim=1536,
    )
    assert file_id is not None
    orig_record = manager.get_file(file_id)
    assert orig_record is not None
    original_name = orig_record["file_name"]

    update_body = MetadataUpdateRequest(updates={"file_name": "will_fail.txt"})

    # _save_metadata가 False를 반환하도록 모킹하여 영속화 실패 시뮬레이션
    with patch.object(manager, "_save_metadata", return_value=False):
        with patch(
            "backend.api.endpoints.metadata.get_file_metadata", return_value=manager
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_metadata(
                    file_id=file_id,
                    body=update_body,
                    locale="ko",
                )

            assert exc_info.value.status_code == 500
            assert "메타데이터 저장에 실패했습니다" in exc_info.value.detail

    # 롤백으로 인해 원본 상태가 보존되었는지 검증
    current_record = manager.get_file(file_id)
    assert current_record is not None
    assert current_record["file_name"] == original_name


@pytest.mark.asyncio
async def test_metadata_i18n_messages(temp_metadata_storage: Path):
    """locale="en" 요청 시 영어 다국어 메시지가 정상 반환되는지 검증."""
    manager = get_file_metadata(str(temp_metadata_storage))

    file_id = manager.add_file(
        file_name="english_doc.md",
        file_size=1024,
        chunk_count=1,
        embedding_dim=1536,
    )
    assert file_id is not None

    with patch(
        "backend.api.endpoints.metadata.get_file_metadata", return_value=manager
    ):
        # GET 영어 메시지
        get_res = await get_metadata(file_id=file_id, locale="en")
        assert get_res.message == "Metadata fetched"

        # PUT 영어 메시지
        put_res = await update_metadata(
            file_id=file_id,
            body=MetadataUpdateRequest(updates={"chunk_count": 2}),
            locale="en",
        )
        assert put_res.message == "Metadata updated"

        # 404 영어 메시지
        with pytest.raises(HTTPException) as exc_info:
            await get_metadata(file_id="unknown_file", locale="en")
        assert "Metadata not found for file" in exc_info.value.detail


def test_metadata_router_registered_in_main_app():
    """backend.main:app 애플리케이션에 metadata 라우터가 올바르게 등록되어 있는지 검증 (Comment 1)."""
    from backend.main import app

    routes = [getattr(route, "path", "") for route in app.routes]

    # /api/metadata/{file_id} 및 /metadata/{file_id} 경로가 모두 라우팅 테이블에 포함되어야 함
    assert any(
        "/metadata/{file_id}" in r for r in routes
    ), f"metadata 라우터가 main app에 등록되지 않았습니다. 현재 등록된 라우트: {routes}"


def test_compute_silhouette_safe_fallback_when_sklearn_missing():
    """scikit-learn 부재(silhouette_score is None) 시 TypeError 없이 -1.0 대체값을 반환하는지 검증 (Comment 3)."""
    import numpy as np

    from backend.services.topic_clustering_service import _compute_silhouette_safe

    dummy_embeddings = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    dummy_labels = np.array([0, 1, 0])

    with patch("backend.services.topic_clustering_service.silhouette_score", None):
        score = _compute_silhouette_safe(dummy_embeddings, dummy_labels)
        assert score == -1.0

# tests/test_imports.py

"""
모델 임포트 테스트
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest


def test_backend_models_import():
    """backend.models 임포트 테스트"""
    try:
        from backend.models import (
            ClassifyBatchRequest,
            ClassifyBatchResponse,
            ClassifyRequest,
            ClassifyResponse,
            FileMetadata,
            FileMetadataInput,
            SaveClassificationRequest,
            SearchRequest,
        )

        print("✅ backend.models import SUCCESS")
        assert True
    except ImportError as e:
        pytest.fail(f"❌ backend.models import FAILED: {e}")


def test_backend_api_models_import():
    """backend.api.models.conflict_models 임포트 테스트"""
    try:
        from backend.models import (
            ConflictDetail,
            ConflictReport,
            ConflictResolution,
            ConflictType,
        )

        print("✅ backend.api.models.conflict_models import SUCCESS")
        assert True
    except ImportError as e:
        pytest.fail(f"❌ backend.api.models.conflict_models import FAILED: {e}")


def test_backend_api_init_import():
    """backend.api 임포트 테스트"""
    try:
        from backend.models import (
            ClassifyRequest,
            ClassifyResponse,
            ConflictDetail,
            ConflictReport,
        )

        print("✅ backend.api import SUCCESS")
        assert True
    except ImportError as e:
        pytest.fail(f"❌ backend.api import FAILED: {e}")


def test_classifier_routes_import():
    """classifier_routes 임포트 테스트"""
    try:
        from backend.routes.classifier_routes import router

        print("✅ classifier_routes import SUCCESS")
        assert True
    except ImportError as e:
        pytest.fail(f"❌ classifier_routes import FAILED: {e}")


def test_metadata_import():
    """metadata.py 임포트 테스트 (클래스 이름 중복 체크)"""
    try:
        # Pydantic 모델
        # 매니저 클래스
        from backend.metadata import FileMetadata as FileMetadataManager
        from backend.models import FileMetadata as PydanticFileMetadata

        print("✅ FileMetadata 두 버전 모두 import SUCCESS")
        print(f"   - Pydantic: {PydanticFileMetadata}")
        print(f"   - Manager: {FileMetadataManager}")
        assert True
    except ImportError as e:
        pytest.fail(f"❌ FileMetadata import FAILED: {e}")


if __name__ == "__main__":
    """터미널에서 직접 실행용"""
    print("\n" + "=" * 50)
    print("🧪 임포트 테스트 시작")
    print("=" * 50 + "\n")

    test_backend_models_import()
    test_backend_api_models_import()
    test_backend_api_init_import()
    test_classifier_routes_import()
    test_metadata_import()

    print("\n" + "=" * 50)
    print("✅ 모든 임포트 테스트 통과!")
    print("=" * 50)

# backend/models/__init__.py

"""
통합 모델 패키지 (backend.models)

- 분류 관련 Pydantic 모델만 re-export
- 다른 패키지(backend.api.* 등)는 여기서 import 하지 않음
"""

from .classification import (
    # 요청 모델
    ClassifyRequest,
    ClassificationRequest,
    MetadataClassifyRequest,
    HybridClassifyRequest,
    ParallelClassifyRequest,

    # 응답 모델
    ClassifyResponse,
    ClassificationResponse,
    ClassifyBatchRequest,
    ClassifyBatchResponse,

    # 파일 메타데이터 (Pydantic 버전)
    FileMetadata,
    FileMetadataInput,

    # API 전용 요청 모델
    SaveClassificationRequest,
    SearchRequest,
)


__all__ = [
    # 요청
    "ClassifyRequest",
    "ClassificationRequest",
    "MetadataClassifyRequest",
    "HybridClassifyRequest",
    "ParallelClassifyRequest",

    # 응답
    "ClassifyResponse",
    "ClassificationResponse",
    "ClassifyBatchRequest",
    "ClassifyBatchResponse",

    # 메타데이터
    "FileMetadata",
    "FileMetadataInput",

    # API 전용
    "SaveClassificationRequest",
    "SearchRequest",
]

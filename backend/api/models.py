# backend/api/models.py - 마이그레이션

"""
Classification models for API layer
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from backend.models import (
    ClassifyRequest,
    ClassifyResponse,
    FileMetadata,
    FileMetadataInput,
    ClassifyBatchResponse,
    SaveClassificationRequest,
    SearchRequest
    )



__all__ = [
    # Classification
    "ClassifyRequest",
    "ClassifyResponse",
    "FileMetadataInput",
    "ClassifyBatchRequest",
    "ClassifyBatchResponse",
    
    # File Management
    "FileMetadata",
    "SaveClassificationRequest",
    "SearchRequest",
]

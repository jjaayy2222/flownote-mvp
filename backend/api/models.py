# backend/api/models.py

"""Pydantic Models for API"""

from pydantic import BaseModel
from typing import Optional, List

class FileMetadata(BaseModel):
    file_id: str
    filename: str
    category: str
    para_class: str
    created_at: Optional[str] = None

class SaveClassificationRequest(BaseModel):
    file_id: str
    classification: dict

class SearchRequest(BaseModel):
    query: str
    filters: Optional[dict] = None

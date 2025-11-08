# backend/routes/conflict_routes.py

"""
분류 API 라우트
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.conflict_service import conflict_service
from typing import List
from backend.api.models import ConflictRecord, ConflictReport
from backend.routes.api_models import ClassifyRequest, ClassifyResponse, MetadataResponse, ErrorResponse

#router = APIRouter(prefix="/api/classify", tags=["classification"])
router = APIRouter()

class ClassifyRequest(BaseModel):
    text: str

class ClassifyResponse(BaseModel):
    #text: str
    para_result: dict
    #keyword_result: dict
    conflict_result: dict
    snapshot_id: str
    #metadata: dict

@router.post("/classify", response_model=ClassifyResponse)
async def classify_text(request: ClassifyRequest):
    """텍스트 분류"""
    try:
        result = conflict_service.classify_text(request.text)
        return {
            "snapshot_id": result["snapshot_id"],
            "para_result": result["para_result"],
            "conflict_result": result["conflict_result"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshots")
async def get_snapshots():
    """저장된 스냅샷 조회"""
    return {"snapshots": conflict_service.get_snapshots()}


@router.post("/resolve")
def resolve_conflicts(conflicts: List[ConflictRecord]) -> ConflictReport:
    """
    충돌 해결 엔드포인트
    """
    from backend.api.endpoints.conflict_resolver_agent import resolve_conflicts_sync
    return resolve_conflicts_sync(conflicts)

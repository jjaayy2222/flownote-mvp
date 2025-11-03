# backend/routes/conflict_routes.py

"""
분류 API 라우트
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/classify", tags=["classification"])

class ClassificationRequest(BaseModel):
    text: str

class ClassificationResponse(BaseModel):
    text: str
    para_result: dict
    keyword_result: dict
    conflict_result: dict
    snapshot_id: str
    metadata: dict

@router.post("/", response_model=ClassificationResponse)
async def classify(request: ClassificationRequest):
    """
    텍스트 분류
    
    Example:
        POST /api/classify/
        {
            "text": "프로젝트 문서 작성"
        }
    """
    try:
        from backend.services.conflict_service import conflict_service
        result = await conflict_service.classify_text(request.text)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/snapshots")
async def get_snapshots():
    """모든 분류 결과 스냅샷 조회"""
    try:
        from backend.services.conflict_service import conflict_service
        snapshots = conflict_service.get_snapshots()
        return {"snapshots": snapshots}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


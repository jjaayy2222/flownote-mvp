# backend/api/endpoints/classify.py

"""Classification Endpoint"""

from fastapi import APIRouter, UploadFile, File

router = APIRouter(prefix="/classify", tags=["classify"])

@router.post("/file")
async def classify_file(file: UploadFile = File(...)):
    """분류 엔드포인트"""
    return {"status": "processing", "file": file.filename}
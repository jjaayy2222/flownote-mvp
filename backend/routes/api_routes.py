# backend/routes/api_routes.py - 마이그레이션

"""
FastAPI 라우터: 통합 버전

DEPRECATED: 이 파일은 Phase 3에서 삭제 예정입니다.
backend/api/endpoints/로 이동되었습니다.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
# 통합 모델 마이그레이션 임포트 
from backend.models.classification import (
    ClassifyResponse,
    SaveClassificationRequest,)
from backend.models.common import(
    SearchRequest,
    SuccessResponse,
    ErrorResponse,
)

from backend.classifier.para_agent import run_para_agent
from backend.metadata import FileMetadata
from backend.chunking import TextChunker
import logging
from datetime import datetime
from typing import Dict
import uuid

logger = logging.getLogger(__name__)

# api_router = APIRouter(prefix="/api", tags=["classification"])
router = APIRouter(prefix="/api", tags=["api"])

metadata_manager = FileMetadata()

chunker = TextChunker(chunk_size=500, chunk_overlap=50)

SAVED_CLASSIFICATIONS = {}



@router.post("/classify/file")
async def classify_file(file: UploadFile = File(...)):
    """파일 분류 - LangGraph 기반!!!"""
    try:
        # 1️⃣ 파일 읽기
        content = await file.read()
        text = content.decode('utf-8')
        filename = file.filename
        
        logger.info(f"🚀 분류 시작: {filename}")
        
        # 2️⃣ 청킹
        chunks = chunker.chunk_text(text)
        chunk_count = len(chunks)
        
        # 3️⃣ 파일 ID 생성 (UUID)
        file_id = f"file_{uuid.uuid4().hex[:8]}"
        
        # 4️⃣ 메타데이터 저장
        try:
            metadata_manager.add_file(
                file_name=filename,
                file_size=len(content),
                chunk_count=chunk_count,
                embedding_dim=1536,
                model="text-embedding-3-small"
            )
            logger.info(f"✅ 메타데이터 저장: {file_id}")
        except Exception as e:
            logger.warning(f"⚠️ 메타데이터 저장 실패 (무시): {e}")
        
        # 5️⃣ LangGraph 기반 고도화 분류!!!
        metadata = {
            "filename": filename,
            "file_size": len(content),
            "chunk_count": chunk_count,
            "uploaded_at": datetime.now().isoformat()
        }
        
        # 처음 2000자만 분류 (비용 절감)
        sample_text = text[:2000]
        
        # 🔥 Sync 버전 호출!
        try:
            para_result = await run_para_agent(
                text=sample_text,
                metadata=metadata
            )
            logger.info(f"✅ 분류 완료: {para_result['category']}")
        except Exception as e:
            logger.error(f"❌ LangGraph 에러: {e}")
            # Fallback
            para_result = {
                "category": "Resources",
                "keyword_tags": sample_text.split()[:10],
                "confidence": 0.5,
                "conflict_detected": False
            }
        
        # 6️⃣ 응답 생성
        response = {
            "final_category": para_result.get('category', 'Resources'),
            "para_category": para_result.get('category', 'Resources'),
            "keyword_tags": para_result.get('keyword_tags', [])[:10],  # 상위 10개만
            "confidence": para_result.get('confidence', 0.5),
            "confidence_gap": para_result.get('confidence_gap', 0.0),
            "conflict_detected": para_result.get('conflict_detected', False),
            "resolution_method": para_result.get('resolution_method', 'auto'),
            "requires_review": para_result.get('requires_review', False),
            # ✅ 메타데이터 추가!
            "metadata": {
                "file_id": file_id,
                "filename": filename,
                "chunk_count": chunk_count,
                "file_size_kb": round(len(content) / 1024, 2),
                "text_preview": sample_text[:100] + "..." if len(sample_text) > 100 else sample_text
            }
        }
        
        return response
        
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="파일 인코딩 오류. UTF-8 파일만 지원합니다.")
    except Exception as e:
        logger.error(f"❌ 분류 에러: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ✅ 엔드포인트 수정 (POST body 사용)
@router.post("/save-classification", response_model=SuccessResponse)
async def save_classification(request: SaveClassificationRequest):
    """분류 결과 저장"""
    try:
        file_id = request.file_id
        classification = request.classification
        
        SAVED_CLASSIFICATIONS[file_id] = {
            "timestamp": datetime.now().isoformat(),
            "classification": classification
        }
        logger.info(f"💾 저장됨: {file_id}")
        return {"status": "saved", "file_id": file_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/saved-files")
async def get_saved_files():
    """저장된 파일 목록"""
    return SAVED_CLASSIFICATIONS


@router.get("/metadata/{file_id}", response_model=Dict)
async def get_metadata(file_id: str):
    """파일 메타데이터 조회"""
    try:
        metadata = metadata_manager.get_file(file_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    """헬스 체크"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}





"""test_result_1 → ❌

    ➀ 임포트 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print('✅ Success!')"`
    ✅ ModelConfig loaded from backend.config
    ✅ Success!

    ➁ 모든 경로 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print([route.path for route in api_router.routes])"`
    ✅ ModelConfig loaded from backend.config
    ['/api/classify']
    
    ➂ `uvicorn backend.main:app --reload --port 8000` ⭕️
    INFO:     Will watch for changes in these directories: ['/Users/jay/ICT-projects/flownote-mvp']
    INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    INFO:     Started reloader process [20749] using StatReload
    INFO:     Started server process [20774]
    INFO:     Waiting for application startup.
    INFO:     Application startup complete.
    INFO:     127.0.0.1:57257 - "POST /api/classify HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59434 - "GET /health HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59621 - "GET /docs HTTP/1.1" 200 OK
    Classification error: asyncio.run() cannot be called from a running event loop
    INFO:     127.0.0.1:52331 - "POST /api/classify HTTP/1.1" 500 Internal Server Error
    /Users/jay/.pyenv/versions/3.11.10/envs/myenv/lib/python3.11/site-packages/starlette/_exception_handler.py:63: RuntimeWarning: coroutine 'run_para_agent' was never awaited
    await response(scope, receive, sender)
    
    ➃ 새 터미널
    - `curl http://localhost:8000/health` ⭕️

    {"status":"✅ API Server is running"}%   

    - `curl http://localhost:8000/docs` ⭕️        # Swagger 문서

        <!DOCTYPE html>
            <html>
            <head>
            <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
            <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
            <title>FlowNote API - Swagger UI</title>
            </head>
            <body>
            <div id="swagger-ui">
            </div>
            <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
            <!-- `SwaggerUIBundle` is now available on the page -->
            <script>
            const ui = SwaggerUIBundle({
                url: '/openapi.json',
            "dom_id": "#swagger-ui",
        "layout": "BaseLayout",
        "deepLinking": true,
        "showExtensions": true,
        "showCommonExtensions": true,
        oauth2RedirectUrl: window.location.origin + '/docs/oauth2-redirect',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
            })
            </script>
            </body>
        </html>
        %             

    - `curl -X POST http://localhost:8000/api/classify \
        -H "Content-Type: application/json" \
        -d '{"text": "프로젝트 완성하기"}'` ❌

    {"detail":"asyncio.run() cannot be called from a running event loop"}%

"""


"""test_result_2 - 동기 함수로 변경 ⭕️

    ➀ 임포트 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print('✅ Success!')"`
    ✅ ModelConfig loaded from backend.config
    ✅ Success!

    ➁ 모든 경로 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print([route.path for route in api_router.routes])"`
    ✅ ModelConfig loaded from backend.config
    ['/api/classify']
    
    ➂ `uvicorn backend.main:app --reload --port 8000` ⭕️
    INFO:     Will watch for changes in these directories: ['/Users/jay/ICT-projects/flownote-mvp']
    INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    INFO:     Started reloader process [20749] using StatReload
    INFO:     Started server process [20774]
    INFO:     Waiting for application startup.
    INFO:     Application startup complete.
    INFO:     127.0.0.1:57257 - "POST /api/classify HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59434 - "GET /health HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59621 - "GET /docs HTTP/1.1" 200 OK

    ➃ 새 터미널
    - `curl http://localhost:8000/health` ⭕️

    {"status":"✅ API Server is running"}%   

    - `curl http://localhost:8000/docs` ⭕️         # Swagger 문서

        <!DOCTYPE html>
            <html>
            <head>
            <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
            <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
            <title>FlowNote API - Swagger UI</title>
            </head>
            <body>
            <div id="swagger-ui">
            </div>
            <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
            <!-- `SwaggerUIBundle` is now available on the page -->
            <script>
            const ui = SwaggerUIBundle({
                url: '/openapi.json',
            "dom_id": "#swagger-ui",
        "layout": "BaseLayout",
        "deepLinking": true,
        "showExtensions": true,
        "showCommonExtensions": true,
        oauth2RedirectUrl: window.location.origin + '/docs/oauth2-redirect',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
            })
            </script>
            </body>
        </html>
        %             

    - `curl -X POST http://localhost:8000/api/classify \
        -H "Content-Type: application/json" \
        -d '{"text": "프로젝트 완성하기"}'` ⭕️

    {"final_category":"Projects","para_category":"Projects",
    "keyword_tags":["프로젝트","완성하기"],"confidence":0.9,
    "confidence_gap":0.3,"conflict_detected":false,
    "resolution_method":"auto_by_confidence","requires_review":false}%       

"""


"""test_result_3 - 통합 버전 테스트 ⭕️

    ➀ 임포트 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print('✅ Success!')"`
    ✅ ModelConfig loaded from backend.config
    ✅ Success!

    ➁ 모든 경로 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print([route.path for route in api_router.routes])"`
    ✅ ModelConfig loaded from backend.config
    ['/api/classify']
    
    ➂ `uvicorn backend.main:app --reload --port 8000` ⭕️
    INFO:     Will watch for changes in these directories: ['/Users/jay/ICT-projects/flownote-mvp']
    INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    INFO:     Started reloader process [20749] using StatReload
    INFO:     Started server process [20774]
    INFO:     Waiting for application startup.
    INFO:     Application startup complete.
    INFO:     127.0.0.1:57257 - "POST /api/classify HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59434 - "GET /health HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59621 - "GET /docs HTTP/1.1" 200 OK

    ➃ 새 터미널
    - `curl http://localhost:8000/health` ⭕️

    {"status":"✅ API Server is running"}%   

    - `curl http://localhost:8000/docs` ⭕️         # Swagger 문서

        <!DOCTYPE html>
            <html>
            <head>
            <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
            <link rel="shortcut icon" href="https://fastapi.tiangolo.com/img/favicon.png">
            <title>FlowNote API - Swagger UI</title>
            </head>
            <body>
            <div id="swagger-ui">
            </div>
            <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
            <!-- `SwaggerUIBundle` is now available on the page -->
            <script>
            const ui = SwaggerUIBundle({
                url: '/openapi.json',
            "dom_id": "#swagger-ui",
        "layout": "BaseLayout",
        "deepLinking": true,
        "showExtensions": true,
        "showCommonExtensions": true,
        oauth2RedirectUrl: window.location.origin + '/docs/oauth2-redirect',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
            })
            </script>
            </body>
        </html>
        %             

    - `curl -X POST http://localhost:8000/api/classify \
        -H "Content-Type: application/json" \
        -d '{"text": "프로젝트 완성하기"}'` ⭕️

    {"final_category":"Projects","para_category":"Projects",
    "keyword_tags":["프로젝트","완성하기"],"confidence":0.9,
    "confidence_gap":0.3,"conflict_detected":false,
    "resolution_method":"auto_by_confidence","requires_review":false}%       

"""


"""test_result_4 - 새로 만든 para_agent_wrapper 테스트 ❌

    ➀ 임포트 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print('✅ Success!')"`
    ✅ ModelConfig loaded from backend.config
    ✅ Success!

    ➁ 모든 경로 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print([route.path for route in api_router.routes])"`
    ✅ ModelConfig loaded from backend.config
    ['/api/classify/file', '/api/save-classification', '/api/saved-files', '/api/metadata/{file_id}', '/api/health']
    
    ➂ `uvicorn backend.main:app --reload --port 8000` ⭕️
    INFO:     Will watch for changes in these directories: ['/Users/jay/ICT-projects/flownote-mvp']
    INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    INFO:     Started reloader process [20749] using StatReload
    INFO:     Started server process [20774]
    INFO:     Waiting for application startup.
    INFO:     Application startup complete.
    INFO:     127.0.0.1:57257 - "POST /api/classify HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59434 - "GET /health HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59621 - "GET /docs HTTP/1.1" 200 OK

    ➃ 새 터미널
    - `curl http://localhost:8000/health` ⭕️

    {"status":"ok"}%   # ← 코드 수정

    - 간단한 텍스트 파일 생성하기
        # 간단한 텍스트 파일 생성
            cat > /tmp/test_file.txt << 'EOF'
            FlowNote PARA 분류기 - 문서 자동 분류 도구

            이 도구는 다음과 같은 기능을 제공합니다:
            1. PARA 시스템 기반 자동 분류
            2. 키워드 추출
            3. 메타데이터 저장
            4. 충돌 자동 해결

            사용 방법:
            1. 파일 업로드
            2. 자동 분류
            3. 결과 저장
            EOF

    - API 호출해보기 ⭕️
    `curl -X POST "http://localhost:8000/api/classify/file" \
        -F "file=@/tmp/test_file.txt"`

    {
        "final_category":"Resources",
        "para_category":"Resources",
        "keyword_tags":["FlowNote", "PARA", "분류기",
                        "-", "문서", "자동", "분류",
                        "도구", "이", "도구는"],
        "confidence":0.5,
        "confidence_gap":0.0,
        "conflict_detected":false,
        "resolution_method":"fallback",
        "requires_review":false
    }%   

    - 분류 결과 저정해보기 ❌
    
    curl -X POST "http://localhost:8000/api/save-classification" \
        -H "Content-Type: application/json" \
        -d '{
            "file_id": "file_123",
            "classification": {
            "final_category": "Resources",
            "confidence": 0.85
            }
        }'

    {"detail":[{"type":"missing","loc":["query","file_id"],"msg":"Field required","input":null}]}%  
    
    - 저장된 파일 조회 ❌

"""


"""test_result_5 - 메타데이터 방식 추가 ⭕️

    ➀ 임포트 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print('✅ Success!')"`
    ✅ ModelConfig loaded from backend.config
    ✅ Success!

    ➁ 모든 경로 테스트 ⭕️ - `python -c "from backend.routes.api_routes import api_router; print([route.path for route in api_router.routes])"`
    ✅ ModelConfig loaded from backend.config
    ['/api/classify/file', '/api/save-classification', '/api/saved-files', '/api/metadata/{file_id}', '/api/health']

    ➂ `uvicorn backend.main:app --reload --port 8000` ⭕️
    INFO:     Will watch for changes in these directories: ['/Users/jay/ICT-projects/flownote-mvp']
    INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
    INFO:     Started reloader process [20749] using StatReload
    INFO:     Started server process [20774]
    INFO:     Waiting for application startup.
    INFO:     Application startup complete.
    INFO:     127.0.0.1:57257 - "POST /api/classify HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59434 - "GET /health HTTP/1.1" 200 OK
    INFO:     127.0.0.1:59621 - "GET /docs HTTP/1.1" 200 OK

    ➃ 새 터미널
    - 파일 분류 시도 with 메타데이터 ⭕️
    `curl -X POST "http://localhost:8000/api/classify/file" \
        -F "file=@/tmp/test_file.txt" | jq '.'`

    % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                    Dload  Upload   Total   Spent    Left  Speed
    100  1104  100   609  100   495  31854  25891 --:--:-- --:--:-- --:--:-- 58105
    {
        "final_category": "Resources",
        "para_category": "Resources",
        "keyword_tags": [
            "FlowNote",
            "PARA",
            "분류기",
            "-",
            "문서",
            "자동",
            "분류",
            "도구",
            "이",
            "도구는"
        ],
        "confidence": 0.5,
        "confidence_gap": 0.0,
        "conflict_detected": false,
        "resolution_method": "fallback",
        "requires_review": false,
        "metadata": {
            "file_id": "file_5f4018bb",
            "filename": "test_file.txt",
            "chunk_count": 1,
            "file_size_kb": 0.29,
            "text_preview": "FlowNote PARA 분류기 - 문서 자동 분류 도구\n\n이 도구는 다음과 같은 기능을 제공합니다:\n1. PARA 시스템 기반 자동 분류\n2. 키워드 추출\n3. 메타데이터 저장\n..."
        }
    }

    - 분류 결과 저장 (POST body로!) ⭕️
    
    `curl -X POST "http://localhost:8000/api/save-classification" \
        -H "Content-Type: application/json" \
        -d '{
            "file_id": "file_abc12345",
            "classification": {
            "final_category": "Resources",
            "confidence": 0.85
            }
        }' | jq '.'`

    % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                    Dload  Upload   Total   Spent    Left  Speed
    100   173  100    44  100   129   5536  16232 --:--:-- --:--:-- --:--:-- 24714
    {
        "status": "saved",
        "file_id": "file_abc12345"
    }

    - 저장된 파일 조회 ⭕️

    `curl "http://localhost:8000/api/saved-files" | jq '.'`
    
    % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                    Dload  Upload   Total   Spent    Left  Speed
    100   126  100   126    0     0  61643      0 --:--:-- --:--:-- --:--:-- 63000
    {
        "file_abc12345": {
            "timestamp": "2025-11-04T13:44:53.809634",
            "classification": {
            "final_category": "Resources",
            "confidence": 0.85
            }
        }
    }
    
    - 헬스 체크 ⭕️    
    `curl "http://localhost:8000/api/health" | jq '.'`

    % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                    Dload  Upload   Total   Spent    Left  Speed
    100    56  100    56    0     0  39660      0 --:--:-- --:--:-- --:--:-- 56000
    {
        "status": "ok",
        "timestamp": "2025-11-04T13:45:11.695864"
    }

"""







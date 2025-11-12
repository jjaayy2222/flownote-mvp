# 📚 `backend/` 구조 및 기술 분석

## 🔍 주요 문제점

### 1. **라우터 중복 및 불일치**
- `api_routes.py` 와 `classifier_routes.py`에 `/classify` 엔드포인트 중복
- `conflict_routes.py`에도 `/classify` 존재
- 각 파일마다 `ClassifyRequest`, `ClassifyResponse` 모델이 중복 정의됨

### 2. **모델 정의 중복**
```python
# api_models.py
class ClassifyRequest(BaseModel): ...
class ClassifyResponse(BaseModel): ...

# classifier_routes.py  
class ClassifyRequest(BaseModel): ...  # 🔴 중복!
class ClassifyResponse(BaseModel): ...  # 🔴 중복!

# conflict_routes.py
class ClassifyRequest(BaseModel): ...  # 🔴 중복!
class ClassifyResponse(BaseModel): ...  # 🔴 중복!
```

### 3. **분류 로직 분산**
- `ConflictService`
- `ParallelClassifier`
- 각 라우터마다 분류 로직 직접 호출

### 4. **데이터 저장 로직 중복**
```python
# classifier_routes.py의 /file 엔드포인트에만 있는 로직:
- CSV 직접 저장
- JSON 로그 저장
- user_context_mapping.json 저장
- DB 저장

# 하지만 /classify 엔드포인트에는 일부만 있음
```

---

## 📋 정리 제안

### **Phase 1: 모델 통합**

#### ✅ `backend/models/` 새 디렉토리 생성
```
backend/
├── models/
│   ├── __init__.py
│   ├── classification.py    # 분류 관련 모델
│   ├── user.py              # 사용자 관련 모델
│   └── common.py            # 공통 모델
```

#### `backend/models/classification.py`
```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# 🎯 통합된 분류 요청 모델
class ClassifyRequest(BaseModel):
    """텍스트 분류 요청 (모든 엔드포인트 공통)"""
    text: str
    user_id: Optional[str] = None
    file_id: Optional[str] = None
    occupation: Optional[str] = None
    areas: Optional[List[str]] = []
    interests: Optional[List[str]] = []

# 🎯 통합된 분류 응답 모델
class ClassifyResponse(BaseModel):
    """분류 응답 (모든 엔드포인트 공통)"""
    category: str
    confidence: float
    keyword_tags: List[str]
    reasoning: str
    snapshot_id: Optional[str] = None
    conflict_detected: bool = False
    requires_review: bool = False
    user_context_matched: bool = False
    user_areas: List[str] = []
    user_context: Dict[str, Any] = {}
    context_injected: bool = False
    log_info: Dict[str, Any] = {}
    csv_log_result: Dict[str, Any] = {}

# 🎯 파일 업로드용 메타데이터
class FileMetadataInput(BaseModel):
    """파일 메타데이터 입력"""
    filename: str
    file_size: int
    user_id: Optional[str] = None
    file_id: Optional[str] = None
```

#### `backend/models/__init__.py`
```python
from .classification import (
    ClassifyRequest,
    ClassifyResponse,
    FileMetadataInput
)
from .user import UserProfile, UserContext

__all__ = [
    "ClassifyRequest",
    "ClassifyResponse", 
    "FileMetadataInput",
    "UserProfile",
    "UserContext"
]
```

---

### **Phase 2: 서비스 계층 통합**

#### ✅ `backend/services/classification_service.py` (신규)
```python
"""
통합 분류 서비스
- 모든 분류 로직을 한 곳에서 관리
- PARA + Keyword + Conflict Resolution
- 로그 저장 통합
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.classifier.para_agent import run_para_agent
from backend.classifier.keyword_classifier import KeywordClassifier
from backend.services.conflict_service import ConflictService
from backend.data_manager import DataManager
from backend.database.metadata_schema import ClassificationMetadataExtender

logger = logging.getLogger(__name__)

class ClassificationService:
    """통합 분류 서비스"""
    
    def __init__(self):
        self.conflict_service = ConflictService()
        self.data_manager = DataManager()
        self.db_extender = ClassificationMetadataExtender()
    
    async def classify_text(
        self,
        text: str,
        user_id: Optional[str] = None,
        file_id: Optional[str] = None,
        occupation: Optional[str] = None,
        areas: Optional[List[str]] = None,
        interests: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        텍스트 분류 (통합 메서드)
        
        Returns:
            {
                "category": str,
                "confidence": float,
                "keyword_tags": List[str],
                "reasoning": str,
                ...
                "log_info": {...}
            }
        """
        # 1. 사용자 컨텍스트 생성
        user_context = self._build_user_context(
            user_id, file_id, occupation, areas, interests
        )
        
        # 2. PARA 분류
        para_result = await run_para_agent(
            text=text,
            metadata=user_context
        )
        
        # 3. 키워드 추출 (매번 새 인스턴스!)
        keyword_classifier = KeywordClassifier()
        keyword_result = await keyword_classifier.aclassify(
            text=text,
            user_context=user_context
        )
        
        # 4. 충돌 해결
        conflict_result = self.conflict_service.classify_text(
            para_result=para_result,
            keyword_result=keyword_result,
            text=text,
            user_context=user_context
        )
        
        # 5. 통합 로그 저장
        log_info = self._save_all_logs(
            user_id=user_id,
            file_id=file_id,
            text=text,
            para_result=para_result,
            keyword_result=keyword_result,
            conflict_result=conflict_result,
            user_context=user_context
        )
        
        # 6. 응답 반환
        return {
            "category": conflict_result.get("final_category"),
            "confidence": conflict_result.get("confidence"),
            "keyword_tags": keyword_result.get("tags", ["기타"]),
            "reasoning": conflict_result.get("reason", ""),
            "snapshot_id": str(para_result.get("snapshot_id", "")),
            "conflict_detected": conflict_result.get("conflict_detected", False),
            "requires_review": conflict_result.get("requires_review", False),
            "user_context_matched": keyword_result.get("user_context_matched", False),
            "user_areas": areas or [],
            "user_context": user_context,
            "context_injected": len(areas or []) > 0,
            "log_info": log_info
        }
    
    def _build_user_context(self, user_id, file_id, occupation, areas, interests):
        """사용자 컨텍스트 생성"""
        return {
            "user_id": user_id or "anonymous",
            "file_id": file_id or "unknown",
            "occupation": occupation or "일반 사용자",
            "areas": areas or [],
            "interests": interests or [],
            "context_keywords": {
                area: [area, f"{area} 관련", f"{area} 업무"]
                for area in (areas or [])
            }
        }
    
    def _save_all_logs(self, **kwargs) -> Dict[str, Any]:
        """통합 로그 저장"""
        log_info = {}
        
        # 1. CSV 로그
        try:
            csv_result = self.data_manager.log_classification(...)
            log_info["csv_saved"] = True
        except Exception as e:
            logger.warning(f"CSV 저장 실패: {e}")
            log_info["csv_saved"] = False
        
        # 2. DB 저장
        try:
            file_id = self.db_extender.save_classification_result(...)
            log_info["db_saved"] = True
            log_info["db_file_id"] = file_id
        except Exception as e:
            logger.warning(f"DB 저장 실패: {e}")
            log_info["db_saved"] = False
        
        # 3. JSON 로그
        # 4. user_context_mapping 업데이트
        
        return log_info

# 싱글톤
_classification_service = None

def get_classification_service() -> ClassificationService:
    global _classification_service
    if _classification_service is None:
        _classification_service = ClassificationService()
    return _classification_service
```

---

### **Phase 3: 라우터 정리**

#### ✅ 라우터 구조 재설계
```
backend/routes/
├── __init__.py
├── classification.py    # 🎯 통합 분류 엔드포인트
├── onboarding.py        # 온보딩
├── metadata.py          # 메타데이터 조회
└── health.py            # 헬스체크
```

#### `backend/routes/classification.py` (통합)
```python
"""
분류 API 라우터 (통합)
- POST /api/classify          # 텍스트 분류
- POST /api/classify/file     # 파일 업로드 분류
- GET  /api/snapshots         # 스냅샷 조회
"""

from fastapi import APIRouter, UploadFile, File, Form
from backend.models import ClassifyRequest, ClassifyResponse
from backend.services.classification_service import get_classification_service

router = APIRouter(prefix="/api/classify", tags=["classification"])
service = get_classification_service()

@router.post("/", response_model=ClassifyResponse)
async def classify_text(request: ClassifyRequest):
    """텍스트 분류"""
    result = await service.classify_text(
        text=request.text,
        user_id=request.user_id,
        file_id=request.file_id,
        occupation=request.occupation,
        areas=request.areas,
        interests=request.interests
    )
    return ClassifyResponse(**result)

@router.post("/file", response_model=ClassifyResponse)
async def classify_file(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    # ... 나머지 Form 파라미터
):
    """파일 업로드 분류"""
    content = await file.read()
    text = content.decode("utf-8")
    
    result = await service.classify_text(
        text=text,
        user_id=user_id,
        # ...
    )
    return ClassifyResponse(**result)

@router.get("/snapshots")
async def get_snapshots():
    """스냅샷 조회"""
    return service.conflict_service.get_snapshots()
```

#### `backend/main.py` (수정)
```python
from backend.routes import classification, onboarding, metadata, health

app = FastAPI(...)

# 라우터 등록
app.include_router(classification.router)
app.include_router(onboarding.router)
app.include_router(metadata.router)
app.include_router(health.router)
```

---

### **Phase 4: 삭제할 파일**

```bash
# 🗑️ 삭제 (중복 및 사용 안 함)
backend/routes/api_routes.py          # → classification.py로 통합
backend/routes/conflict_routes.py      # → classification.py로 통합
backend/routes/api_models.py           # → backend/models/로 이동
backend/api/models.py                  # → backend/models/로 이동

# 🗑️ 삭제 고려
backend/api/__init__.py                # api/ 디렉토리 자체 제거
backend/api/endpoints/*.py             # 라우터로 통합됨
```

---

### **Phase 5: 추가 개선사항**

#### 1. **DataManager 개선**
```python
# backend/data_manager.py
class DataManager:
    def save_classification_complete(
        self,
        user_id: str,
        file_id: str,
        classification_result: Dict,
        save_to_csv: bool = True,
        save_to_db: bool = True,
        save_to_json: bool = True
    ) -> Dict[str, Any]:
        """
        통합 저장 메서드
        - CSV, DB, JSON 로그를 한 번에 처리
        - 각 저장 성공/실패 여부 반환
        """
        results = {}
        
        if save_to_csv:
            results["csv"] = self.log_classification(...)
        
        if save_to_db:
            results["db"] = self._save_to_db(...)
        
        if save_to_json:
            results["json"] = self._save_to_json(...)
        
        return results
```

#### 2. **Config 통합**
```python
# backend/config.py에 추가
class PathConfig:
    """경로 설정"""
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    
    # 각 데이터 타입별 디렉토리
    USERS_DIR = DATA_DIR / "users"
    CONTEXT_DIR = DATA_DIR / "context"
    CLASSIFICATIONS_DIR = DATA_DIR / "classifications"
    LOG_DIR = DATA_DIR / "log"
    
    # 파일 경로
    USERS_CSV = USERS_DIR / "users_profiles.csv"
    CONTEXT_JSON = CONTEXT_DIR / "user_context_mapping.json"
    CLASSIFICATIONS_CSV = CLASSIFICATIONS_DIR / "classification_log.csv"
    
    @classmethod
    def ensure_directories(cls):
        """모든 디렉토리 생성"""
        for attr in dir(cls):
            value = getattr(cls, attr)
            if isinstance(value, Path) and attr.endswith("_DIR"):
                value.mkdir(parents=True, exist_ok=True)
```

---

## 📊 정리 순서 (우선순위)

### **1단계 (즉시)**: 모델 통합
- [ ] `backend/models/` 디렉토리 생성
- [ ] 중복 모델 통합
- [ ] 모든 라우터에서 `from backend.models import ...` 사용

### **2단계 (중요)**: 서비스 계층 생성
- [ ] `ClassificationService` 구현
- [ ] 로그 저장 로직 통합
- [ ] 기존 라우터에서 서비스 호출로 변경

### **3단계**: 라우터 통합
- [ ] `classification.py` 생성
- [ ] 기존 라우터 코드 이동
- [ ] 중복 엔드포인트 제거

### **4단계**: 정리
- [ ] 사용 안 하는 파일 삭제
- [ ] 테스트 실행
- [ ] 문서 업데이트

---

## 🎯 예상 효과

1. **코드 중복 50% 감소**
2. **유지보수성 향상** (로직이 한 곳에)
3. **테스트 용이** (서비스 계층 테스트)
4. **확장성 향상** (새 엔드포인트 추가 쉬움)

---
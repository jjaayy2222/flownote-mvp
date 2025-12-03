# FlowNote v4.0 Service Layer 아키텍처

> **작성일**: 2025-12-03  
> **버전**: v4.0 Phase 1 - `step 2/5`
> **패턴**: Service Layer Pattern

---

## 🏗️ 아키텍처 개요

### 계층 구조

```
┌──────────────────────────────────────────────────────┐
│  Presentation Layer (Routes)                         │
│  - HTTP 요청/응답 처리                                │
│  - 입력 검증 (Pydantic)                               │
│  - 상태 코드 관리                                     │
└──────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────┐
│  Service Layer (Business Logic)                      │
│  - 분류 오케스트레이션 (ClassificationService)        │
│  - 충돌 해결 (ConflictService)                        │
│  - 온보딩 플로우 (OnboardingService)                  │
└──────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────┐
│  Domain Layer (Classifiers & Utilities)              │
│  - BaseClassifier (추상 클래스)                       │
│  - KeywordClassifier (키워드 매칭)                    │
│  - PARA Agent (LLM 기반 분류)                         │
│  - ConflictResolver (충돌 해결 로직)                  │
└──────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────┐
│  Data Layer (Models & Database)                      │
│  - Pydantic Models                                    │
│  - Database Schema                                    │
│  - Data Manager                                       │
└──────────────────────────────────────────────────────┘
```

---

## 📁 Service Layer 구조

```
backend/services/
├── __init__.py                    # 서비스 모듈 초기화
├── classification_service.py      # 분류 오케스트레이션
├── conflict_service.py            # 충돌 해결
├── onboarding_service.py          # 온보딩 플로우
├── gpt_helper.py                  # GPT API 헬퍼
└── parallel_processor.py          # 병렬 처리 (미사용)
```

---

## 🔵 ClassificationService

### 책임
- PARA 분류 오케스트레이션
- 키워드 추출
- 충돌 해결 조정
- 결과 저장 및 로깅

### 의존성
```python
from backend.services.conflict_service import ConflictService
from backend.data_manager import DataManager
from backend.classifier.para_agent import run_para_agent
from backend.classifier.keyword import KeywordClassifier
```

### 주요 메서드

#### `async classify()`
```python
async def classify(
    self,
    text: str,
    user_id: str = None,
    file_id: str = None,
    occupation: str = None,
    areas: list = None,
    interests: list = None,
) -> ClassifyResponse:
    """
    통합 분류 메서드 (Main Entry Point)
    
    흐름:
    1. 사용자 컨텍스트 구성
    2. PARA 분류 실행
    3. 키워드 추출 실행
    4. 충돌 해결
    5. 최종 카테고리 결정
    6. 결과 저장 (CSV + JSON)
    7. 응답 생성
    """
```

### 내부 메서드

#### `_build_user_context()`
```python
def _build_user_context(
    self, user_id, occupation, areas, interests
) -> dict:
    """
    사용자 컨텍스트 구성
    
    Returns:
        {
            "user_id": str,
            "occupation": str,
            "areas": list,
            "interests": list,
            "context_keywords": dict
        }
    """
```

#### `async _run_para_classification()`
```python
async def _run_para_classification(
    self, text: str, metadata: dict
) -> dict:
    """
    PARA 분류 실행
    
    - run_para_agent() 호출
    - 에러 시 Fallback 반환
    """
```

#### `async _extract_keywords()`
```python
async def _extract_keywords(
    self, text: str, user_context: dict
) -> dict:
    """
    키워드 추출
    
    - KeywordClassifier 인스턴스 생성
    - classify() 호출
    - 태그 안전 처리
    """
```

#### `async _resolve_conflicts()`
```python
async def _resolve_conflicts(
    self, para_result: dict, keyword_result: dict,
    text: str, user_context: dict
) -> dict:
    """
    충돌 해결
    
    - ConflictService.classify_text() 호출
    - 최종 카테고리 결정
    """
```

#### `_save_results()`
```python
def _save_results(
    self, user_id: str, file_id: str,
    final_category: str, keyword_tags: list,
    confidence: float, snapshot_id: str
) -> dict:
    """
    결과 저장 (CSV + JSON)
    
    - data/classifications/classification_log.csv
    - data/log/classification_{timestamp}.json
    """
```

### 사용 예시

```python
# Route에서 호출
classification_service = ClassificationService()

result = await classification_service.classify(
    text="프로젝트 완성하기",
    user_id="user_001",
    occupation="개발자",
    areas=["코드 품질"],
)
```

---

## 🟡 ConflictService

### 책임
- PARA + Keyword 통합 분류
- 충돌 감지 및 해결
- 스냅샷 관리

### 의존성
```python
from backend.classifier.para_agent import run_para_agent
from backend.classifier.keyword import KeywordClassifier
from backend.classifier.conflict_resolver import ConflictResolver
from backend.classifier.snapshot_manager import SnapshotManager
```

### 주요 메서드

#### `async classify_text()`
```python
async def classify_text(
    self, 
    text: str,
    para_result: Optional[Dict] = None,
    keyword_result: Optional[Dict] = None,
    user_context: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    텍스트 통합 분류
    
    흐름:
    1. PARA 분류 (없으면 실행)
    2. Keyword 분류 (없으면 실행)
    3. Conflict Resolution
    4. Snapshot 저장
    5. 최종 결과 반환
    """
```

#### `async _resolve_conflict_async()`
```python
async def _resolve_conflict_async(
    self,
    para_result: Dict,
    keyword_result: Dict,
    text: str
) -> Dict:
    """
    충돌 해결 (ConflictResolver 사용)
    
    - ClassificationResult 객체 생성
    - ConflictResolver.resolve() 호출
    """
```

### 스냅샷 관리

```python
def get_snapshots() -> list:
    """모든 스냅샷 조회"""

def get_snapshot(snapshot_id: str) -> dict:
    """특정 스냅샷 조회"""

def compare_snapshots(id1: str, id2: str) -> dict:
    """2개 스냅샷 비교"""

def clear_snapshots():
    """모든 스냅샷 삭제"""
```

---

## 🟢 OnboardingService

### 책임
- 사용자 프로필 생성
- AI 기반 영역 추천
- 사용자 컨텍스트 저장
- 온보딩 상태 관리

### 의존성
```python
from backend.services.gpt_helper import GPT4oHelper
from backend.data_manager import DataManager
```

### 주요 메서드

#### `create_user()`
```python
def create_user(
    self, occupation: str, name: str = None
) -> dict:
    """
    사용자 프로필 생성
    
    Returns:
        {
            "status": "success",
            "user_id": str,
            "occupation": str,
            "name": str
        }
    """
```

#### `suggest_areas()`
```python
def suggest_areas(
    self, user_id: str, occupation: str
) -> dict:
    """
    AI 기반 영역 추천
    
    - GPT-4o 호출
    - 직업 기반 PARA Areas 추천
    
    Returns:
        {
            "status": "success",
            "suggested_areas": list
        }
    """
```

#### `save_user_context()`
```python
def save_user_context(
    self, user_id: str, selected_areas: list
) -> dict:
    """
    사용자 컨텍스트 저장
    
    - 선택된 영역 저장
    - 컨텍스트 키워드 생성
    
    Returns:
        {
            "status": "success",
            "context_keywords": dict
        }
    """
```

#### `get_user_status()`
```python
def get_user_status(self, user_id: str) -> dict:
    """
    온보딩 상태 확인
    
    Returns:
        {
            "status": "success",
            "is_completed": bool,
            "occupation": str,
            "areas": list
        }
    """
```

---

## 🎨 설계 패턴

### 1. Service Layer Pattern
- **목적**: 비즈니스 로직을 Presentation Layer에서 분리
- **장점**: 재사용성, 테스트 용이성, 유지보수성

### 2. Dependency Injection
```python
class ClassificationService:
    def __init__(self):
        self.conflict_service = ConflictService()
        self.data_manager = DataManager()
```

### 3. Async/Await
```python
async def classify(self, text: str, ...):
    para_result = await self._run_para_classification(...)
    keyword_result = await self._extract_keywords(...)
    conflict_result = await self._resolve_conflicts(...)
```

### 4. Error Handling
```python
try:
    result = await service_method(...)
    return result
except Exception as e:
    logger.error(f"❌ 오류: {e}")
    return fallback_result()
```

---

## 📊 Service Layer 통계

| Service | 파일 크기 | 주요 메서드 수 | 의존성 수 |
|---------|----------|---------------|----------|
| ClassificationService | 265줄 | 7 | 4 |
| ConflictService | 230줄 | 8 | 4 |
| OnboardingService | 182줄 | 4 | 2 |

---

## 🔄 데이터 흐름

### 분류 요청 흐름
```
User Request
    ↓
Route (classifier_routes.py)
    ↓
ClassificationService.classify()
    ↓ (병렬 실행)
    ├─→ PARA Agent (LLM 분류)
    └─→ KeywordClassifier (키워드 매칭)
    ↓
ConflictService.classify_text()
    ↓
ConflictResolver.resolve()
    ↓
SnapshotManager.save_snapshot()
    ↓
DataManager.log_classification()
    ↓
ClassifyResponse
    ↓
User Response
```

---

## 🧪 테스트 전략

### Unit Tests
```python
# tests/unit/services/test_classification_service.py
@pytest.mark.asyncio
async def test_classification_service():
    service = ClassificationService()
    result = await service.classify(
        text="테스트",
        user_id="test_user"
    )
    assert result.category in ["Projects", "Areas", "Resources", "Archives"]
```

### Integration Tests
```python
# tests/integration/services/test_classification_flow.py
@pytest.mark.asyncio
async def test_full_classification_flow():
    # 온보딩 → 분류 → 충돌 해결 전체 흐름 테스트
    pass
```

---

## 🚀 향후 개선 사항

### Phase 2
- [ ] RuleEngine 통합
- [ ] AIClassifier 추가
- [ ] ConfidenceCalculator 구현

### Phase 3
- [ ] MCP 통합 (Obsidian, Notion)
- [ ] 외부 도구 동기화

### Phase 4
- [ ] Celery 자동화
- [ ] 주기적 재분류
- [ ] 자동 아카이빙

---

**작성자**: Jay  
**최종 수정**: 2025-12-03

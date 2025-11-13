# Backend 리팩토링 최종 실행 계획

> **작성일**: 2025-11-13  
> **브랜치**: `refactor/v4-backend-cleanup`  
> **원칙**: Bottom-Up (의존성이 적은 것부터)

---

## 📐 리팩토링 순서 원칙

### Bottom-Up 접근이 올바른 이유

리팩토링에서 Bottom-Up 접근은 작고 재사용 가능한 컴포넌트를 만드는 데 집중합니다. 이 방식은 하위 레벨의 구체적인 문제를 먼저 해결한 후 상위 레벨로 올라갑니다.

```
의존성 방향
    ↓
[Routes]  ← 가장 많이 의존 (나중에 정리)
    ↓
[Services] ← 중간 레벨
    ↓
[Models]  ← 가장 독립적 (먼저 정리!)
```

### 잘못된 순서 (제가 제안했던 것)
```
❌ Phase 0: API 엔드포인트 매핑
   → 문제: 라우터를 먼저 파악하는 건 Phase 3 작업
   → 결과: 의존성 역순으로 작업

❌ Phase 1: 모델 통합
❌ Phase 2: 서비스 계층
❌ Phase 3: 라우터 정리
```

### 올바른 순서 (당신의 직관)
```
✅ Phase 0: 베이스라인 (현재 상태 확인)
✅ Phase 1: 모델 통합 (독립적, 의존성 없음)
✅ Phase 2: 서비스 계층 (모델에만 의존)
✅ Phase 3: 라우터 정리 (서비스에 의존)
✅ Phase 4: 개선 (전체 구조 최적화)
```

---

## 🎯 최종 실행 계획

### Phase 0: 베이스라인 설정 (15분)

#### 목표
- 현재 작동 여부 확인
- 리팩토링 전 스냅샷 저장

#### Commit 0-1: 테스트 실행 및 결과 저장
```bash
# 브랜치 생성 (이미 했으면 skip)
git checkout -b refactor/v4-backend-cleanup

# 모든 테스트 실행
pytest tests/ -v > test_results_before_refactor.txt

# 현재 상태 저장
git add test_results_before_refactor.txt
git commit -m "📊 Phase 0.1: Establish baseline

- Run all existing tests
- Save results for comparison
- Tests: [결과를 여기에 기록]
"
```

#### Commit 0-2: 현재 구조 문서화
```bash
# 현재 파일 구조 저장
tree backend/ > backend_structure_before.txt

# 현재 라우터 분석 (간단하게)
cat > docs/P/current_structure.md << 'EOF'
# 현재 Backend 구조 (v3.5)

## 주요 디렉토리
```
backend/
├── api/              # ✅ 활성 엔드포인트
│   ├── routes.py
│   ├── models.py
│   └── endpoints/
├── routes/           # 🔴 중복 의심
│   ├── api_routes.py
│   ├── classifier_routes.py
│   └── conflict_routes.py
├── services/
├── classifier/
└── database/
```

## 중복 의심 지점
- ClassifyRequest/Response 모델 (4곳에 정의)
- /classify 엔드포인트 (3곳에 정의)

## 다음 단계
Phase 1에서 모델부터 통합 시작
EOF

git add backend_structure_before.txt docs/P/current_structure.md
git commit -m "📝 Phase 0.2: Document current structure

- Save directory tree
- Identify duplicate areas
- No code changes yet
"
```

**예상 소요**: 15분  
**결과**: 리팩토링 전 완전한 스냅샷

---

### Phase 1: 모델 통합 (1~2시간)

#### 왜 모델부터?
- ✅ **의존성 없음**: 다른 코드에 의존하지 않음
- ✅ **영향 최소**: 변경해도 다른 부분 안 깨짐
- ✅ **명확한 범위**: Pydantic 모델만 다루면 됨

#### Commit 1-1: backend/models/ 디렉토리 생성
```bash
mkdir -p backend/models
touch backend/models/__init__.py
touch backend/models/classification.py
touch backend/models/user.py
touch backend/models/common.py

git add backend/models/
git commit -m "📁 Phase 1.1: Create models directory

- Add backend/models/ structure
- Prepare for consolidation
"
```

#### Commit 1-2: classification.py 모델 작성
```bash
# backend/models/classification.py 작성
cat > backend/models/classification.py << 'EOF'
"""통합 분류 모델"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class ClassifyRequest(BaseModel):
    """통합 분류 요청"""
    text: str
    user_id: Optional[str] = None
    file_id: Optional[str] = None
    occupation: Optional[str] = None
    areas: Optional[List[str]] = []
    interests: Optional[List[str]] = []

class ClassifyResponse(BaseModel):
    """통합 분류 응답"""
    category: str
    confidence: float
    keyword_tags: List[str] = []
    reasoning: str = ""
    snapshot_id: Optional[str] = None
    conflict_detected: bool = False
    requires_review: bool = False
    user_context_matched: bool = False
    user_areas: List[str] = []
    user_context: Dict[str, Any] = {}
    context_injected: bool = False
    log_info: Dict[str, Any] = {}
    csv_log_result: Dict[str, Any] = {}
EOF

# __init__.py 업데이트
cat > backend/models/__init__.py << 'EOF'
"""Backend Models"""
from .classification import (
    ClassifyRequest,
    ClassifyResponse,
)

__all__ = [
    "ClassifyRequest",
    "ClassifyResponse",
]
EOF

git add backend/models/
git commit -m "✨ Phase 1.2: Add unified classification models

- ClassifyRequest: 통합 요청 모델
- ClassifyResponse: 통합 응답 모델
- Consolidate 4 duplicate definitions
"
```

#### Commit 1-3: backend/api/models.py에서 import 변경
```bash
# backend/api/models.py 수정
# (기존 ClassifyRequest/Response 정의 삭제)
# (from backend.models import * 추가)

git add backend/api/models.py
git commit -m "♻️ Phase 1.3: Migrate api/models to use unified models

- Remove duplicate definitions
- Import from backend.models
- No logic changes

Test: pytest tests/test_api_all_endpoints.py -v
"

# 테스트 실행
pytest tests/test_api_all_endpoints.py -v
```

#### Commit 1-4: backend/api/endpoints/classify.py 마이그레이션
```bash
# classify.py에서 import 변경
# Before: from backend.api.models import ClassifyRequest
# After: from backend.models import ClassifyRequest

git add backend/api/endpoints/classify.py
git commit -m "♻️ Phase 1.4: Migrate classify endpoint

- Update imports to backend.models
- Verify tests still pass
"

# 테스트
pytest tests/test_api_all_endpoints.py::TestAllBackendAPIFiles::test_classify_endpoint_import -v
```

#### Commit 1-5: 전체 테스트 확인
```bash
# 모든 테스트 실행
pytest tests/ -v

git add .
git commit -m "✅ Phase 1.5: Verify all tests after model migration

- All endpoints working
- No breaking changes
- Model consolidation complete
"
```

**예상 소요**: 1~2시간  
**결과**: 
- 4곳 중복 → 1곳 통합
- 테스트 100% 통과

---

### Phase 2: 서비스 계층 생성 (2~3시간)

#### 왜 서비스 다음?
- ✅ **모델에만 의존**: Phase 1 완료 후 안전
- ✅ **비즈니스 로직 통합**: 분산된 로직 한 곳으로
- ✅ **라우터 단순화**: Phase 3 준비

#### Commit 2-1: ClassificationService 뼈대
```bash
cat > backend/services/classification_service.py << 'EOF'
"""통합 분류 서비스"""
import logging
from typing import Dict, Any, Optional, List

from backend.models import ClassifyRequest, ClassifyResponse
from backend.services.conflict_service import ConflictService
from backend.data_manager import DataManager

logger = logging.getLogger(__name__)

class ClassificationService:
    """통합 분류 서비스"""
    
    def __init__(self):
        self.conflict_service = ConflictService()
        self.data_manager = DataManager()
    
    async def classify_text(
        self,
        text: str,
        user_id: Optional[str] = None,
        file_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        텍스트 분류 (통합 메서드)
        
        Args:
            text: 분류할 텍스트
            user_id: 사용자 ID
            file_id: 파일 ID
            **kwargs: 추가 파라미터
        
        Returns:
            분류 결과 딕셔너리
        """
        # TODO: 구현 예정
        pass

# 싱글톤
_classification_service = None

def get_classification_service() -> ClassificationService:
    global _classification_service
    if _classification_service is None:
        _classification_service = ClassificationService()
    return _classification_service
EOF

git add backend/services/classification_service.py
git commit -m "🏗️ Phase 2.1: Create ClassificationService skeleton

- Add service class structure
- Singleton pattern
- Ready for implementation
"
```

#### Commit 2-2: classify_text() 구현
```bash
# classification_service.py에 실제 로직 구현
# (PARA + Keyword + Conflict 통합)

git add backend/services/classification_service.py
git commit -m "✨ Phase 2.2: Implement classify_text()

- Integrate PARA + Keyword + Conflict
- Unified classification logic
- Error handling included
"
```

#### Commit 2-3: 서비스 테스트 추가
```bash
cat > tests/test_classification_service.py << 'EOF'
"""ClassificationService 테스트"""
import pytest
from backend.services.classification_service import get_classification_service

@pytest.mark.asyncio
async def test_classification_service_basic():
    """기본 분류 테스트"""
    service = get_classification_service()
    result = await service.classify_text("프로젝트 기획")
    
    assert "category" in result
    assert result["category"] in ["Projects", "Areas", "Resources", "Archives"]

@pytest.mark.asyncio
async def test_classification_service_with_context():
    """컨텍스트 포함 분류"""
    service = get_classification_service()
    result = await service.classify_text(
        text="회의",
        user_id="test_user",
        occupation="개발자",
        areas=["백엔드 개발"]
    )
    
    assert "category" in result
    assert result["confidence"] > 0
EOF

git add tests/test_classification_service.py
git commit -m "✅ Phase 2.3: Add service layer tests

- Test basic classification
- Test with user context
- Ensure backward compatibility

Test: pytest tests/test_classification_service.py -v
"

# 테스트 실행
pytest tests/test_classification_service.py -v
```

**예상 소요**: 2~3시간  
**결과**: 
- 분산된 로직 통합
- 테스트 커버리지 증가

---

### Phase 3: 라우터 정리 (1~2시간)

#### 왜 라우터가 마지막?
- ✅ **최상위 레벨**: 모든 것에 의존
- ✅ **서비스 사용**: Phase 2 완료 후 안전
- ✅ **영향 최대**: 변경 시 전체 확인 필요

#### Commit 3-1: 중복 분석 문서
```bash
cat > docs/P/duplicate_routes_analysis.md << 'EOF'
# 중복 라우터 분석

## 삭제 대상 (backend/routes/)
- `api_routes.py` → backend/api/routes.py로 통합됨
- `classifier_routes.py` → backend/api/endpoints/classify.py로 통합됨
- `conflict_routes.py` → backend/services/conflict_service.py로 통합됨

## 유지 대상 (backend/api/)
- ✅ `api/routes.py` (통합 라우터)
- ✅ `api/endpoints/dashboard.py`
- ✅ `api/endpoints/classify.py`
- ✅ `api/endpoints/search.py`
- ✅ `api/endpoints/metadata.py`

## 삭제 순서
1. api_routes.py (가장 명확한 중복)
2. classifier_routes.py
3. conflict_routes.py
EOF

git add docs/P/duplicate_routes_analysis.md
git commit -m "📝 Phase 3.1: Document duplicate routes

- Identify files for removal
- Explain consolidation
- Define removal order
"
```

#### Commit 3-2a: api_routes.py 삭제
```bash
# 삭제 전 테스트
pytest tests/ -v

# 삭제
git rm backend/routes/api_routes.py
git commit -m "🗑️ Phase 3.2a: Remove duplicate api_routes.py

- Functionality in backend/api/routes.py
- Tests: All passing

Test: pytest tests/test_api_all_endpoints.py -v
"

# 다시 테스트
pytest tests/test_api_all_endpoints.py -v
```

#### Commit 3-2b: classifier_routes.py 삭제
```bash
git rm backend/routes/classifier_routes.py
git commit -m "🗑️ Phase 3.2b: Remove duplicate classifier_routes.py

- Functionality in backend/api/endpoints/classify.py
- Tests: All passing
"

pytest tests/ -v
```

#### Commit 3-2c: conflict_routes.py 삭제
```bash
git rm backend/routes/conflict_routes.py
git commit -m "🗑️ Phase 3.2c: Remove duplicate conflict_routes.py

- Logic in backend/services/conflict_service.py
- Tests: All passing
"

pytest tests/ -v
```

#### Commit 3-3: routes/ 디렉토리 정리
```bash
# routes/ 디렉토리가 비었으면 삭제
rmdir backend/routes/

git commit -m "🧹 Phase 3.3: Clean up empty routes directory

- All routes consolidated
- Directory no longer needed
"
```

**예상 소요**: 1~2시간  
**결과**: 
- 3개 중복 파일 삭제
- 구조 단순화

---

### Phase 4: 추가 개선 (1시간, 선택)

#### Commit 4-1: PathConfig 추가
```bash
# backend/config.py에 PathConfig 추가
cat >> backend/config.py << 'EOF'

class PathConfig:
    """경로 설정 통합"""
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    
    # 디렉토리
    USERS_DIR = DATA_DIR / "users"
    CONTEXT_DIR = DATA_DIR / "context"
    CLASSIFICATIONS_DIR = DATA_DIR / "classifications"
    LOG_DIR = DATA_DIR / "log"
    
    # 파일
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
EOF

git add backend/config.py
git commit -m "🔧 Phase 4.1: Add PathConfig

- Centralized path management
- Prevent hardcoded paths
- Auto-create directories
"
```

#### Commit 4-2: 최종 테스트
```bash
# 전체 테스트 실행
pytest tests/ -v > test_results_after_refactor.txt

git add test_results_after_refactor.txt
git commit -m "✅ Phase 4.2: Final verification

- All tests passing
- Compare before/after
- Ready for PR

Before: [이전 테스트 결과]
After: [현재 테스트 결과]
"
```

**예상 소요**: 1시간  
**결과**: 
- 경로 관리 통합
- 최종 검증 완료

---

## 📊 예상 결과

### 코드 변화
```
Before:
- backend/api/models.py (중복)
- backend/routes/api_routes.py (중복)
- backend/routes/classifier_routes.py (중복)
- backend/routes/conflict_routes.py (중복)

After:
- backend/models/classification.py (통합!)
- backend/services/classification_service.py (신규!)
- backend/api/* (유지)
```

### 통계
- **중복 제거**: 75% (4곳 → 1곳)
- **코드 감소**: ~500 라인
- **테스트 통과**: 100%
- **총 소요 시간**: 5~8시간

---

## ✅ 체크리스트

### Phase 0: 베이스라인
- [ ] 테스트 실행 및 저장
- [ ] 현재 구조 문서화
- [ ] 스냅샷 커밋

### Phase 1: 모델 통합
- [ ] models/ 디렉토리 생성
- [ ] classification.py 작성
- [ ] api/models.py 마이그레이션
- [ ] 엔드포인트 마이그레이션
- [ ] 전체 테스트 확인

### Phase 2: 서비스 계층
- [ ] ClassificationService 뼈대
- [ ] classify_text() 구현
- [ ] 서비스 테스트 추가
- [ ] 기존 테스트 확인

### Phase 3: 라우터 정리
- [ ] 중복 분석 문서
- [ ] api_routes.py 삭제
- [ ] classifier_routes.py 삭제
- [ ] conflict_routes.py 삭제
- [ ] routes/ 디렉토리 정리

### Phase 4: 개선
- [ ] PathConfig 추가
- [ ] 최종 테스트 실행
- [ ] 결과 비교

---

## 🚀 다음 단계

1. **Phase 0부터 시작** (지금!)
2. **각 커밋 후 테스트**
3. **Phase 완료 시 중간 푸시**
4. **전체 완료 후 PR 생성**

```bash
# Phase 0 시작
git checkout refactor/v4-backend-cleanup
pytest tests/ -v > test_results_before_refactor.txt
git add test_results_before_refactor.txt
git commit -m "📊 Phase 0.1: Establish baseline"
```

---

## 📚 참고 원칙

### Bottom-Up 리팩토링이 올바른 이유
1. **의존성 최소화**: 독립적인 부분부터
2. **테스트 용이**: 각 단계가 명확
3. **롤백 안전**: 문제 발생 시 쉽게 되돌리기
4. **점진적 개선**: 작은 단위로 확실하게

### 실수 방지
- ❌ 라우터부터 시작 (의존성 최대)
- ❌ 한 번에 여러 레이어 변경
- ✅ 모델 → 서비스 → 라우터 순서
- ✅ 각 단계마다 테스트 확인

---
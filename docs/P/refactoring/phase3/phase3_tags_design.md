# Phase 3: Tags 구조 설계

## 📊 통합 현황

### Before Phase 3
```
    backend/routes/
    ├── api_routes.py (5개 엔드포인트)
    ├── classifier_routes.py (8개 엔드포인트)
    └── conflict_routes.py (snapshots 포함)

    Total: 14개 엔드포인트 (3개 파일)
```

### After Phase 3
```
    backend/routes/
    ├── classifier_routes.py (14개 엔드포인트) ← 모두 통합!
    ├── onboarding_routes.py (그대로)
    └── conflict_routes.py (snapshots 제외)

    Total: 14개 엔드포인트 (1개 파일로 통합!)
```

---

## 🎯 최종 엔드포인트 구조

### classifier_routes.py (14개)

#### Section 1: Main API (2개)
```
POST /classify/classify              [Classification > Main API > Text]
POST /classify/file                  [Classification > Main API > File Upload]
```

#### Section 2: Advanced API (4개)
```
POST /classify/advanced/file         [Classification > Advanced > LangGraph]
POST /classify/save-classification   [Classification > Storage > Save]
GET  /classify/saved-files           [Classification > Storage > List]
GET  /classify/metadata/{file_id}    [Classification > Metadata > Query]
```

#### Section 3: Specialized Methods (6개)
```
POST /classify/text                  [Classification > Specialized > LangChain Only]
POST /classify/metadata              [Classification > Specialized > Metadata Based]
POST /classify/hybrid                [Classification > Specialized > Hybrid]
POST /classify/parallel              [Classification > Specialized > Parallel]
POST /classify/para                  [Classification > Specialized > PARA]
POST /classify/keywords              [Classification > Specialized > Keywords]
```

#### Section 4: History (1개)
```
GET  /classify/snapshots             [Classification > History > Query]
```

---

## 🎯 Tags 3단계 구조 (대분류 > 중분류 > 소분류)

### 원칙
- **대분류**: 서비스 전체를 나누는 최상위 분류
- **중분류**: 주요 기능 단위
- **소분류**: 세부 기능, 특정 모델, 특정 타입

### 🏷️ Tags 구조

#### 대분류 (Category)
- Classification

#### 중분류 (Feature)
- Main API (핵심 기능)
- Advanced (고급 기능)
- Storage (저장)
- Metadata (메타데이터)
- Specialized (특화 메서드)
- History (이력)

#### 소분류 (Detail)
- Text, File Upload
- LangGraph, Save, List, Query
- LangChain Only, Metadata Based, Hybrid, Parallel, PARA, Keywords

---

## ✅ 달성한 목표

### 1. 모든 엔드포인트 보존
- ✅ api_routes.py의 5개 엔드포인트 모두 통합
- ✅ classifier_routes.py의 8개 엔드포인트 유지
- ✅ conflict_routes.py의 snapshots 이동

### 2. Prefix로 명확히 구분
```
/classify/file              (Main API)
/classify/advanced/file     (Advanced API)
```

### 3. Tags 3단계 구조
```python
tags=["Classification", "Main API", "Text"]
      # 대분류        중분류        소분류
```

### 4. Snapshots 이동
```
Before: /conflicts/snapshots
After:  /classify/snapshots
```

---

## 📈 성과 측정

### 코드 통합
- Before: 3개 파일에 분산
- After: 1개 파일로 통합
- 유지보수성: ⬆️ 향상

### 구조 개선
- Before: prefix 불명확, tags 없음
- After: prefix 명확, tags 3단계
- 가독성: ⬆️ 향상

### 문서화
- Before: 주석 부족
- After: 명확한 주석, 출처 표시
- 이해도: ⬆️ 향상

---

## 🎨 Swagger UI 구조

```
Classification
│
├─ Main API
│  ├─ POST /classify [Text]
│  └─ POST /file [File Upload]
│
├─ Advanced
│  └─ POST /advanced/file [LangGraph]
│
├─ Storage
│  ├─ POST /save-classification [Save]
│  └─ GET /saved-files [List]
│
├─ Metadata
│  └─ GET /metadata/{file_id} [Query]
│
├─ Specialized
│  ├─ POST /text [LangChain Only]
│  ├─ POST /metadata [Metadata Based]
│  ├─ POST /hybrid [Hybrid]
│  ├─ POST /parallel [Parallel]
│  ├─ POST /para [PARA]
│  └─ POST /keywords [Keywords]
│
└─ History
   └─ GET /snapshots [Query]
```

---

## 🔧 기술 세부사항

### 함수명 구분
```python
# Main API
async def classify_file_main(...)     # 기존 classifier_routes.py

# Advanced API
async def classify_file_advanced(...)  # 기존 api_routes.py
```

### Import 경로
```python
# 통합된 import
from backend.models import (
    ClassifyRequest,
    ClassifyResponse,
    # ... 모든 모델
)

from backend.classifier.para_agent import run_para_agent
from backend.services.conflict_service import ConflictService
# ... 모든 서비스
```

### 섹션 구분
```python
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 1: Main API (기존 classifier_routes.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📦 Section 2: Advanced API (기존 api_routes.py에서 이동)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---
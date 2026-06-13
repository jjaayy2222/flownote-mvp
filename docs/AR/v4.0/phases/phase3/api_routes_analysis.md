# api_routes.py 분석

## 엔드포인트 목록

```bash

    (myenv) ➜  flownote-mvp git:(refactor-v4-phase-4-routes) cat backend/routes/api_routes.py | grep -E "@router\.(get|post|put|delete)"
    @router.post("/classify/file")
    @router.post("/save-classification", response_model=SuccessResponse)
    @router.get("/saved-files")
    @router.get("/metadata/{file_id}", response_model=Dict)
    @router.get("/health")

```

### 1. POST /api/save-classification
- **기능**: 분류 결과 저장
- **중복 여부**: classifier_routes.py에 동일 기능 존재
- **조치**: 삭제

### 2. POST /api/search
- **기능**: 파일 검색
- **중복 여부**: classifier_routes.py에 동일 기능 존재
- **조치**: 삭제

### 3. GET /api/metadata/{file_id}
- **기능**: 메타데이터 조회
- **중복 여부**: classifier_routes.py에 동일 기능 존재
- **조치**: 삭제

## 결론
✅ **모든 기능이 classifier_routes.py에 존재**
✅ **안전하게 삭제 가능**

<br>

---

## 🎯 통합 목표 목표

### 핵심 원칙
```
✅ 모든 엔드포인트 보존 (아무것도 버리지 않음!)
✅ prefix로 구분 (/classify vs /classify/advanced/file)
✅ Tags 3단계 구조 (대분류 > 중분류 > 소분류)
✅ Snapshots도 classifier_routes.py로 이동
```


### 통합 전후 비교

**통합 전:**
```
backend/routes/
├── api_routes.py (5개 엔드포인트)
│   └── POST /api/classify/file
│   └── POST /api/save-classification
│   └── GET  /api/saved-files
│   └── GET  /api/metadata/{file_id}
│   └── GET  /api/health (main.py로 이동)
│
├── classifier_routes.py (8개 엔드포인트)
│   └── POST /classify
│   └── POST /file
│   └── POST /text
│   └── POST /metadata
│   └── POST /hybrid
│   └── POST /parallel
│   └── POST /para
│   └── POST /keywords
│
└── conflict_routes.py
    └── GET /conflicts/snapshots

Total: 14개 엔드포인트 (3개 파일)
```

**통합 후:**
```
backend/routes/
├── classifier_routes.py (14개 엔드포인트) ← 모두 통합!
│   ├─ Section 1: Main API (2개)
│   │   └── POST /classify/classify
│   │   └── POST /classify/file
│   │
│   ├─ Section 2: Advanced API (4개)
│   │   └── POST /classify/advanced/file
│   │   └── POST /classify/save-classification
│   │   └── GET  /classify/saved-files
│   │   └── GET  /classify/metadata/{file_id}
│   │
│   ├─ Section 3: Specialized Methods (6개)
│   │   └── POST /classify/text
│   │   └── POST /classify/metadata
│   │   └── POST /classify/hybrid
│   │   └── POST /classify/parallel
│   │   └── POST /classify/para
│   │   └── POST /classify/keywords
│   │
│   └─ Section 4: History (1개)
│       └── GET /classify/snapshots (conflict_routes에서 이동)
│
├── onboarding_routes.py (그대로)
└── conflict_routes.py (snapshots 제외)

Total: 14개 엔드포인트 (1개 파일로 통합!)
```

<br>

---

## 📋 통합

```
    통합 구조 분석
        ↓
    Tags 3단계 구조 최종 설계
        ↓
    통합 파일 완성
        ↓
    api_routes.py 제거 & main.py 수정
        ↓
    기타 파일 수정
        ↓
    전체 테스트
        ↓
    커밋 & 문서화
```

---
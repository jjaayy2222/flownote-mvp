# FlowNote Backend 리팩토링 계획

> **작성일**: 2025-11-13  
> **상태**: 계획 단계  
> **예상 소요**: 3~5일 (마이크로 커밋 방식)

---

## 📌 현재 상황

Claude를 통해 backend/ 전체 분석 완료. 주요 개선 영역 4가지 발견:

1. **라우터 중복** (`api_routes.py`, `classifier_routes.py`, `conflict_routes.py`에 `/classify` 중복)
2. **모델 중복** (`ClassifyRequest`, `ClassifyResponse`가 여러 파일에 중복 정의)
3. **분류 로직 분산** (여러 서비스에 로직이 흩어짐)
4. **데이터 저장 로직 중복** (CSV, JSON, DB 저장 로직이 각 라우터마다 다름)

---

## 🎯 목표

- **중복 제거**: 코드 중복 50% 감소
- **유지보수성**: 로직을 한 곳에 집중
- **테스트 용이성**: 서비스 계층 독립 테스트
- **확장성**: 새 기능 추가 시 일관된 패턴

---

## 🚀 Workflow 1: 모델 통합 (1~2일)

### 목표
중복된 Pydantic 모델들을 `backend/models/`로 통합

### 작업 항목

#### Commit 1: models/ 디렉토리 구조 생성
```bash
git checkout -b refactor/phase1-models

mkdir -p backend/models
touch backend/models/__init__.py
touch backend/models/classification.py
touch backend/models/user.py
touch backend/models/common.py

git add backend/models/
git commit -m "📁 Create backend/models/ directory structure

- Add models/__init__.py
- Add classification.py (empty)
- Add user.py (empty)
- Add common.py (empty)

Related: #refactor-phase1"
```

#### Commit 2: classification.py 모델 정의
```bash
# backend/models/classification.py 작성
# (Claude가 제안한 ClassifyRequest, ClassifyResponse 등)

git add backend/models/classification.py
git commit -m "✨ Add unified classification models

- ClassifyRequest: 통합 분류 요청 모델
- ClassifyResponse: 통합 분류 응답 모델  
- FileMetadataInput: 파일 업로드 메타데이터

모든 중복 모델을 하나로 통합

Related: #refactor-phase1"
```

#### Commit 3: user.py 모델 정의
```bash
git add backend/models/user.py
git commit -m "✨ Add user-related models

- UserProfile: 사용자 프로필
- UserContext: 사용자 컨텍스트

Related: #refactor-phase1"
```

#### Commit 4: __init__.py 업데이트
```bash
git add backend/models/__init__.py
git commit -m "🔧 Update models/__init__.py with exports

Export all model classes for easy import

Related: #refactor-phase1"
```

#### Commit 5: classifier_routes.py 마이그레이션
```bash
# classifier_routes.py에서 모델 import 변경
# from pydantic import BaseModel → from backend.models import ClassifyRequest

git add backend/routes/classifier_routes.py
git commit -m "♻️ Migrate classifier_routes to use unified models

- Remove duplicate ClassifyRequest, ClassifyResponse
- Import from backend.models
- No logic changes

Related: #refactor-phase1"
```

#### Commit 6: api_routes.py 마이그레이션
```bash
git add backend/routes/api_routes.py
git commit -m "♻️ Migrate api_routes to use unified models

- Remove duplicate model definitions
- Import from backend.models

Related: #refactor-phase1"
```

#### Commit 7: conflict_routes.py 마이그레이션
```bash
git add backend/routes/conflict_routes.py
git commit -m "♻️ Migrate conflict_routes to use unified models

- Remove duplicate model definitions
- Import from backend.models

Related: #refactor-phase1"
```

#### Commit 8: 테스트 실행 & PR
```bash
# 테스트 실행
pytest tests/

# 성공하면
git push origin refactor/phase1-models

# GitHub에서 PR 생성:
# Title: "Phase 1: 모델 통합 (Refactor Models)"
# Body: "중복된 Pydantic 모델들을 backend/models/로 통합"
```

---

## 🚀 Workflow 2: 서비스 계층 생성 (1~2일)

### 목표
분산된 분류 로직을 `ClassificationService`로 통합

### 작업 항목

#### Commit 1: classification_service.py 뼈대 생성
```bash
git checkout -b refactor/phase2-service

touch backend/services/classification_service.py

git add backend/services/classification_service.py
git commit -m "🏗️ Create ClassificationService skeleton

- Add empty ClassificationService class
- Add singleton pattern

Related: #refactor-phase2"
```

#### Commit 2: classify_text() 메서드 구현
```bash
git add backend/services/classification_service.py
git commit -m "✨ Implement ClassificationService.classify_text()

- Integrate PARA + Keyword + Conflict resolution
- Unified classification logic

Related: #refactor-phase2"
```

#### Commit 3: 로그 저장 로직 통합
```bash
git add backend/services/classification_service.py
git commit -m "✨ Add unified logging in ClassificationService

- _save_all_logs(): CSV + DB + JSON 통합
- Centralized error handling

Related: #refactor-phase2"
```

#### Commit 4: classifier_routes에서 서비스 사용
```bash
# classifier_routes.py에서 직접 호출 → service.classify_text() 호출

git add backend/routes/classifier_routes.py
git commit -m "♻️ Use ClassificationService in classifier_routes

- Replace direct logic with service.classify_text()
- Simplify route handlers

Related: #refactor-phase2"
```

#### Commit 5: api_routes에서 서비스 사용
```bash
git add backend/routes/api_routes.py
git commit -m "♻️ Use ClassificationService in api_routes

- Replace duplicate logic with service calls

Related: #refactor-phase2"
```

#### Commit 6: 테스트 & PR
```bash
pytest tests/

git push origin refactor/phase2-service

# PR: "Phase 2: 서비스 계층 생성 (Classification Service)"
```

---

## 🚀 Workflow 3: 라우터 정리 (1일)

### 목표
중복 라우터 통합 + 삭제

### 작업 항목

#### Commit 1: classification.py 통합 라우터 생성
```bash
git checkout -b refactor/phase3-routes

# 새 파일 생성
touch backend/routes/classification.py

git add backend/routes/classification.py
git commit -m "✨ Create unified classification router

- Consolidate /classify endpoints
- POST /api/classify
- POST /api/classify/file
- GET /api/snapshots

Related: #refactor-phase3"
```

#### Commit 2: main.py 라우터 등록 업데이트
```bash
git add backend/main.py
git commit -m "🔧 Update router registration in main.py

- Use new classification.router
- Remove old routers

Related: #refactor-phase3"
```

#### Commit 3: 중복 파일 삭제
```bash
git rm backend/routes/api_routes.py
git rm backend/routes/conflict_routes.py
git rm backend/api_models.py

git commit -m "🗑️ Remove duplicate route files

- Delete api_routes.py (merged to classification.py)
- Delete conflict_routes.py (merged to classification.py)
- Delete api_models.py (moved to backend/models/)

Related: #refactor-phase3"
```

#### Commit 4: 테스트 & PR
```bash
pytest tests/

git push origin refactor/phase3-routes

# PR: "Phase 3: 라우터 정리 (Consolidate Routes)"
```

---

## 🚀 Workflow 4: 추가 개선 (선택사항, 1일)

### 목표
DataManager 개선 + Config 정리

### 작업 항목

#### Commit 1: DataManager에 통합 저장 메서드 추가
```bash
git checkout -b refactor/phase4-improvements

git add backend/data_manager.py
git commit -m "✨ Add save_classification_complete() to DataManager

- Unified save method (CSV + DB + JSON)
- Return success/failure status

Related: #refactor-phase4"
```

#### Commit 2: PathConfig 추가
```bash
git add backend/config.py
git commit -m "🔧 Add PathConfig for centralized path management

- DATA_DIR, USERS_DIR, etc.
- ensure_directories() method

Related: #refactor-phase4"
```

#### Commit 3: 테스트 & PR
```bash
pytest tests/

git push origin refactor/phase4-improvements

# PR: "Phase 4: 추가 개선사항"
```

---

## 📊 진행 체크리스트

### Phase 1: 모델 통합
- [ ] models/ 디렉토리 생성
- [ ] classification.py 작성
- [ ] user.py 작성
- [ ] 라우터들 마이그레이션
- [ ] 테스트 통과
- [ ] PR 생성 & Merge

### Phase 2: 서비스 계층
- [ ] ClassificationService 생성
- [ ] classify_text() 구현
- [ ] 로그 저장 통합
- [ ] 라우터에서 서비스 사용
- [ ] 테스트 통과
- [ ] PR 생성 & Merge

### Phase 3: 라우터 정리
- [ ] classification.py 통합 라우터
- [ ] main.py 업데이트
- [ ] 중복 파일 삭제
- [ ] 테스트 통과
- [ ] PR 생성 & Merge

### Phase 4: 추가 개선
- [ ] DataManager 개선
- [ ] PathConfig 추가
- [ ] 테스트 통과
- [ ] PR 생성 & Merge

---

## 🎯 예상 효과

- **코드 중복 50% ↓**
- **유지보수 시간 30% ↓**
- **테스트 커버리지 20% ↑**
- **새 기능 추가 속도 40% ↑**

---

## 📝 참고사항

### 각 Workflow 시작 전
1. `main` 브랜치에서 최신 코드 pull
2. 새 브랜치 생성 (`refactor/phase*-*`)
3. 작은 단위로 커밋 (마이크로 커밋)

### 각 Workflow 완료 후
1. 테스트 실행 (`pytest`)
2. PR 생성 (GitHub)
3. 코드 리뷰 (자가 리뷰 or 팀)
4. Merge to main
5. 로컬 브랜치 삭제

### 커밋 메시지 규칙
- ✨ `:sparkles:` - 새 기능
- ♻️ `:recycle:` - 리팩토링
- 🔧 `:wrench:` - 설정 파일
- 🗑️ `:wastebasket:` - 파일 삭제
- 🏗️ `:building_construction:` - 구조 변경
- 📁 `:file_folder:` - 디렉토리 생성

---

## 🚨 주의사항

1. **절대 main에 직접 커밋 금지**
2. **각 Phase는 독립적으로 동작해야 함**
3. **테스트 실패 시 절대 Merge 금지**
4. **data/ 폴더 경로 변경 주의** (기존 데이터 유지)
5. **매 커밋마다 테스트 실행 권장**

---

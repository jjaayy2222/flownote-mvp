# FlowNote v4.0 Route 구조 문서

> **작성일**: 2025-12-03  
> **버전**: v4.0 Phase 1 - `step 2/5`
> **패턴**: Thin Router Pattern

---

## 🏗️ 아키텍처 개요

### Thin Router 패턴

FlowNote v4.0은 **Thin Router** 패턴을 채택하여 관심사를 명확히 분리합니다.

```
┌─────────────────────────────────────┐
│  Routes (Thin Router)               │
│  - 요청/응답 처리만 담당             │
│  - HTTP 상태 코드 관리               │
│  - 입력 검증 (Pydantic)              │
└─────────────────────────────────────┘
           ↓ 위임
┌─────────────────────────────────────┐
│  Services (Business Logic)          │
│  - 분류 로직                         │
│  - 충돌 해결                         │
│  - 온보딩 플로우                     │
└─────────────────────────────────────┘
           ↓ 사용
┌─────────────────────────────────────┐
│  Classifiers & Utilities            │
│  - BaseClassifier                   │
│  - KeywordClassifier                │
│  - PARA Agent                       │
└─────────────────────────────────────┘
```

---

## 📁 Route 파일 구조

```
backend/routes/
├── __init__.py              # Router 통합
├── classifier_routes.py     # 분류 관련 엔드포인트
├── conflict_routes.py       # 충돌 해결 엔드포인트
├── onboarding_routes.py     # 온보딩 엔드포인트
└── api_models.py            # Conflict 전용 모델
```

---

## 🔗 Route 상세

### 1. Classification Routes

**파일**: `backend/routes/classifier_routes.py` (182줄)

**서비스**: `ClassificationService`

**엔드포인트**:

#### POST `/classifier/classify`
- **설명**: 텍스트 PARA 분류
- **요청**: `ClassifyRequest`
  ```json
  {
    "text": "프로젝트 완성하기",
    "user_id": "user_001",
    "occupation": "개발자",
    "areas": ["코드 품질", "기술 역량"],
    "interests": ["AI", "백엔드"]
  }
  ```
- **응답**: `ClassifyResponse`
  ```json
  {
    "category": "Projects",
    "confidence": 0.85,
    "snapshot_id": "snap_20251203_105500",
    "keyword_tags": ["프로젝트", "완성"],
    "reasoning": "명확한 목표와 마감일 관련 키워드 감지",
    "user_context_matched": true
  }
  ```

#### POST `/classifier/file`
- **설명**: 파일 업로드 후 분류
- **요청**: Multipart Form Data
  - `file`: 업로드 파일
  - `user_id`: 사용자 ID (Form)
  - `occupation`: 직업 (Form)
  - `areas`: JSON 문자열 (Form)
- **응답**: `ClassifyResponse`

**특징**:
- ✅ Thin Router 패턴 완벽 적용
- ✅ 모든 로직을 ClassificationService로 위임
- ✅ 깔끔한 에러 핸들링

---

### 2. Conflict Routes

**파일**: `backend/routes/conflict_routes.py` (56줄)

**서비스**: `ConflictService`

**엔드포인트**:

#### POST `/conflict/resolve`
- **설명**: 충돌 레코드 일괄 해결
- **요청**: `List[ConflictRecord]`
  ```json
  [
    {
      "id": "conflict_1",
      "para_category": "Projects",
      "keyword_category": "Areas",
      "confidence_gap": 0.15
    }
  ]
  ```
- **응답**: `ConflictReport`

#### GET `/conflict/snapshots`
- **설명**: 저장된 스냅샷 조회 (디버깅용)
- **응답**: 스냅샷 목록

**특징**:
- ✅ 디버깅 및 분석 목적
- ✅ 수동 충돌 해결 인터페이스
- ✅ 간결한 구조

---

### 3. Onboarding Routes

**파일**: `backend/routes/onboarding_routes.py` (180줄)

**서비스**: `OnboardingService`

**엔드포인트**:

#### POST `/onboarding/step1`
- **설명**: 사용자 프로필 생성
- **요청**: `Step1Input`
  ```json
  {
    "name": "홍길동",
    "occupation": "소프트웨어 엔지니어"
  }
  ```
- **응답**:
  ```json
  {
    "status": "success",
    "user_id": "user_20251203_001",
    "occupation": "소프트웨어 엔지니어",
    "next_step": "/onboarding/suggest-areas?user_id=..."
  }
  ```

#### GET `/onboarding/suggest-areas`
- **설명**: AI 기반 관심 영역 추천
- **파라미터**: 
  - `user_id`: 사용자 ID
  - `occupation`: 직업
- **응답**:
  ```json
  {
    "status": "success",
    "suggested_areas": [
      "코드 품질 관리",
      "기술 역량 개발",
      "팀 협업",
      "프로젝트 관리"
    ]
  }
  ```

#### POST `/onboarding/save-context`
- **설명**: 사용자 컨텍스트 저장
- **요청**: `Step2Input`
  ```json
  {
    "user_id": "user_20251203_001",
    "selected_areas": ["코드 품질 관리", "기술 역량 개발"]
  }
  ```
- **응답**:
  ```json
  {
    "status": "success",
    "message": "컨텍스트 저장 완료",
    "context_keywords": {
      "코드 품질 관리": ["코드", "품질", "리뷰"],
      "기술 역량 개발": ["기술", "학습", "성장"]
    }
  }
  ```

#### GET `/onboarding/status/{user_id}`
- **설명**: 온보딩 상태 확인
- **응답**:
  ```json
  {
    "status": "success",
    "is_completed": true,
    "occupation": "소프트웨어 엔지니어",
    "areas": ["코드 품질 관리", "기술 역량 개발"]
  }
  ```

**특징**:
- ✅ Thin Router 패턴 적용
- ✅ 4단계 온보딩 플로우
- ✅ GPT-4o 기반 AI 추천

---

## 🎨 설계 원칙

### 1. 단일 책임 원칙 (SRP)
- **Routes**: HTTP 요청/응답만 처리
- **Services**: 비즈니스 로직 담당
- **Classifiers**: 분류 알고리즘 구현

### 2. 의존성 주입
```python
# 싱글톤 서비스 인스턴스
classification_service = ClassificationService()

@router.post("/classify")
async def classify_text(request: ClassifyRequest):
    return await classification_service.classify(...)
```

### 3. 타입 안정성
- Pydantic 모델로 요청/응답 검증
- 타입 힌트 적용

### 4. 에러 핸들링
```python
try:
    result = await service.method(...)
    return result
except Exception as e:
    logger.error(f"❌ 오류: {e}")
    raise HTTPException(status_code=500, detail=str(e))
```

---

## 📊 통계

| Route 파일 | 라인 수 | 엔드포인트 수 | 서비스 |
|-----------|---------|--------------|--------|
| classifier_routes.py | 182 | 2 | ClassificationService |
| conflict_routes.py | 56 | 2 | ConflictService |
| onboarding_routes.py | 180 | 4 | OnboardingService |
| **합계** | **418** | **8** | **3** |

---

## 🔄 마이그레이션 히스토리

### Before (Fat Router)
```python
@router.post("/classify")
async def classify_text(request: ClassifyRequest):
    # 500줄의 비즈니스 로직이 여기에...
    para_result = await run_para_agent(...)
    keyword_result = await KeywordClassifier().classify(...)
    conflict_result = await resolve_conflict(...)
    # ...
```

### After (Thin Router)
```python
@router.post("/classify")
async def classify_text(request: ClassifyRequest):
    # 단 3줄!
    return await classification_service.classify(
        text=request.text, user_id=request.user_id, ...
    )
```

**개선 효과**:
- ✅ 가독성 향상
- ✅ 테스트 용이성 증가
- ✅ 유지보수성 개선
- ✅ 재사용성 증가

---

## 🚀 다음 단계

1. **Phase 2**: Hybrid Classifier 구현
2. **Phase 3**: MCP 통합 (Obsidian, Notion)
3. **Phase 4**: Celery 자동화

---

**작성자**: Jay 
**최종 수정**: 2025-12-03

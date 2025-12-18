# FlowNote v4.0 API 엔드포인트 목록

> **작성일**: 2025-12-03  
> **버전**: v4.0 Phase 1  - `step 2/5` 
> **Base URL**: `http://localhost:8000`

---

## 📋 전체 엔드포인트 요약

| 카테고리 | 엔드포인트 | 메서드 | 설명 |
|---------|-----------|--------|------|
| **Classification** | `/classifier/classify` | POST | 텍스트 PARA 분류 |
| **Classification** | `/classifier/file` | POST | 파일 업로드 분류 |
| **Conflict** | `/conflict/resolve` | POST | 충돌 해결 |
| **Conflict** | `/conflict/snapshots` | GET | 스냅샷 조회 |
| **Onboarding** | `/onboarding/step1` | POST | 사용자 생성 |
| **Onboarding** | `/onboarding/suggest-areas` | GET | 영역 추천 (AI) |
| **Onboarding** | `/onboarding/save-context` | POST | 컨텍스트 저장 |
| **Onboarding** | `/onboarding/status/{user_id}` | GET | 온보딩 상태 확인 |

---

## 🔵 Classification API

### 1. 텍스트 분류

```http
POST /classifier/classify
Content-Type: application/json
```

**Request Body**:
```json
{
  "text": "프로젝트 완성하기",
  "user_id": "user_001",
  "file_id": "file_001",
  "occupation": "소프트웨어 엔지니어",
  "areas": ["코드 품질 관리", "기술 역량 개발"],
  "interests": ["AI", "백엔드 개발"]
}
```

**Response** (200 OK):
```json
{
  "category": "Projects",
  "confidence": 0.85,
  "snapshot_id": "snap_20251203_105500_123",
  "conflict_detected": false,
  "requires_review": false,
  "keyword_tags": ["프로젝트", "완성", "task"],
  "reasoning": "명확한 목표와 마감일 관련 키워드 감지",
  "user_context_matched": true,
  "user_areas": ["코드 품질 관리", "기술 역량 개발"],
  "user_context": {
    "user_id": "user_001",
    "occupation": "소프트웨어 엔지니어",
    "areas": ["코드 품질 관리", "기술 역량 개발"],
    "interests": ["AI", "백엔드 개발"]
  },
  "context_injected": true,
  "log_info": {
    "csv_saved": true,
    "json_saved": true,
    "csv_path": "data/classifications/classification_log.csv",
    "json_path": "classification_20251203_105500_123.json"
  }
}
```

**cURL 예시**:
```bash
curl -X POST "http://localhost:8000/classifier/classify" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "프로젝트 완성하기",
    "user_id": "user_001",
    "occupation": "개발자",
    "areas": ["코드 품질"]
  }'
```

---

### 2. 파일 업로드 분류

```http
POST /classifier/file
Content-Type: multipart/form-data
```

**Request (Form Data)**:
```
file: (binary file)
user_id: user_001
file_id: document_001
occupation: 개발자
areas: ["코드 품질", "기술 역량"]
interests: ["AI"]
```

**Response** (200 OK):
```json
{
  "category": "Projects",
  "confidence": 0.82,
  "snapshot_id": "snap_20251203_105600_456",
  "keyword_tags": ["개발", "프로젝트"],
  "reasoning": "파일 내용 기반 분류",
  "user_context_matched": true
}
```

**cURL 예시**:
```bash
curl -X POST "http://localhost:8000/classifier/file" \
  -F "file=@document.txt" \
  -F "user_id=user_001" \
  -F 'areas=["코드 품질"]'
```

---

## 🟡 Conflict API

### 3. 충돌 해결

```http
POST /conflict/resolve
Content-Type: application/json
```

**Request Body**:
```json
[
  {
    "id": "conflict_1",
    "para_category": "Projects",
    "keyword_category": "Areas",
    "confidence_gap": 0.15
  },
  {
    "id": "conflict_2",
    "para_category": "Resources",
    "keyword_category": "Projects",
    "confidence_gap": 0.08
  }
]
```

**Response** (200 OK):
```json
{
  "total_conflicts": 2,
  "resolved_count": 2,
  "failed_count": 0,
  "resolutions": [
    {
      "id": "conflict_1",
      "final_category": "Projects",
      "method": "confidence_based",
      "confidence": 0.85
    },
    {
      "id": "conflict_2",
      "final_category": "Projects",
      "method": "user_context",
      "confidence": 0.78
    }
  ]
}
```

---

### 4. 스냅샷 조회

```http
GET /conflict/snapshots
```

**Response** (200 OK):
```json
{
  "snapshots": [
    {
      "id": "snap_20251203_105500_123",
      "timestamp": "2025-12-03T10:55:00",
      "text": "프로젝트 완성하기",
      "para_result": {
        "category": "Projects",
        "confidence": 0.9
      },
      "keyword_result": {
        "tags": ["프로젝트", "완성"],
        "confidence": 0.8
      },
      "conflict_result": {
        "final_category": "Projects",
        "conflict_detected": false
      }
    }
  ]
}
```

---

## 🟢 Onboarding API

### 5. Step 1: 사용자 생성

```http
POST /onboarding/step1
Content-Type: application/json
```

**Request Body**:
```json
{
  "name": "홍길동",
  "occupation": "소프트웨어 엔지니어"
}
```

**Response** (200 OK):
```json
{
  "status": "success",
  "user_id": "user_20251203_001",
  "occupation": "소프트웨어 엔지니어",
  "name": "홍길동",
  "created_at": "2025-12-03T10:55:00",
  "next_step": "/onboarding/suggest-areas?user_id=user_20251203_001&occupation=소프트웨어 엔지니어"
}
```

**cURL 예시**:
```bash
curl -X POST "http://localhost:8000/onboarding/step1" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "홍길동",
    "occupation": "소프트웨어 엔지니어"
  }'
```

---

### 6. Step 2: 영역 추천 (AI)

```http
GET /onboarding/suggest-areas?user_id={user_id}&occupation={occupation}
```

**Parameters**:
- `user_id`: 사용자 ID (required)
- `occupation`: 직업 (required)

**Response** (200 OK):
```json
{
  "status": "success",
  "user_id": "user_20251203_001",
  "occupation": "소프트웨어 엔지니어",
  "suggested_areas": [
    "코드 품질 관리",
    "기술 역량 개발",
    "팀 협업 및 커뮤니케이션",
    "프로젝트 관리",
    "시스템 아키텍처 설계"
  ],
  "message": "GPT-4o 기반 추천 완료"
}
```

**cURL 예시**:
```bash
curl -X GET "http://localhost:8000/onboarding/suggest-areas?user_id=user_20251203_001&occupation=소프트웨어%20엔지니어"
```

---

### 7. Step 3: 컨텍스트 저장

```http
POST /onboarding/save-context
Content-Type: application/json
```

**Request Body**:
```json
{
  "user_id": "user_20251203_001",
  "selected_areas": [
    "코드 품질 관리",
    "기술 역량 개발"
  ]
}
```

**Response** (200 OK):
```json
{
  "status": "success",
  "user_id": "user_20251203_001",
  "message": "컨텍스트 저장 완료",
  "selected_areas": [
    "코드 품질 관리",
    "기술 역량 개발"
  ],
  "context_keywords": {
    "코드 품질 관리": [
      "코드 품질 관리",
      "코드 품질 관리 관련",
      "코드 품질 관리 업무",
      "코드 품질 관리 프로젝트"
    ],
    "기술 역량 개발": [
      "기술 역량 개발",
      "기술 역량 개발 관련",
      "기술 역량 개발 업무",
      "기술 역량 개발 프로젝트"
    ]
  },
  "onboarding_completed": true
}
```

---

### 8. Step 4: 온보딩 상태 확인

```http
GET /onboarding/status/{user_id}
```

**Response** (200 OK):
```json
{
  "status": "success",
  "user_id": "user_20251203_001",
  "is_completed": true,
  "occupation": "소프트웨어 엔지니어",
  "areas": [
    "코드 품질 관리",
    "기술 역량 개발"
  ],
  "created_at": "2025-12-03T10:55:00",
  "updated_at": "2025-12-03T10:56:30"
}
```

**Response** (404 Not Found - 사용자 없음):
```json
{
  "status": "error",
  "message": "사용자를 찾을 수 없습니다."
}
```

---

## 🔴 에러 응답

### 400 Bad Request
```json
{
  "detail": "Invalid input: text field is required"
}
```

### 404 Not Found
```json
{
  "detail": "User not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "분류 실패: Internal server error"
}
```

---

## 📊 응답 시간 (평균)

| 엔드포인트 | 평균 응답 시간 |
|-----------|---------------|
| `/classifier/classify` | ~0.5s |
| `/classifier/file` | ~0.8s |
| `/conflict/resolve` | ~0.3s |
| `/onboarding/suggest-areas` | ~2.0s (GPT-4o 호출) |
| `/onboarding/save-context` | ~0.2s |

---

## 🧪 테스트 시나리오

### 시나리오 1: 완전한 온보딩 플로우
```bash
# Step 1: 사용자 생성
USER_ID=$(curl -X POST "http://localhost:8000/onboarding/step1" \
  -H "Content-Type: application/json" \
  -d '{"name": "테스터", "occupation": "개발자"}' \
  | jq -r '.user_id')

# Step 2: 영역 추천
curl -X GET "http://localhost:8000/onboarding/suggest-areas?user_id=$USER_ID&occupation=개발자"

# Step 3: 컨텍스트 저장
curl -X POST "http://localhost:8000/onboarding/save-context" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$USER_ID\", \"selected_areas\": [\"코드 품질\"]}"

# Step 4: 분류 테스트
curl -X POST "http://localhost:8000/classifier/classify" \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"프로젝트 완성\", \"user_id\": \"$USER_ID\"}"
```

---

## 📖 OpenAPI 문서

**Swagger UI**: `http://localhost:8000/docs`  
**ReDoc**: `http://localhost:8000/redoc`

---

**작성자**: Jay
**최종 수정**: 2025-12-03

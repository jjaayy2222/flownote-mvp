# `backend/routes/classsifier_routes.py` 통합 테스트 

## 기본 테스트

### 모델 import
```bash
# 1. 모델 import
    python -c "
    from backend.models import (
        ClassifyRequest, ClassifyResponse,
        Step1Input, OnboardingStatus,
        ErrorResponse, HealthCheckResponse,
        ConflictRecord
    )
    print('✅ Models import OK')"

    ✅ Models import OK
```

### 라우터 import
```bash
# 2. 라우터 import
    python -c "
    from backend.routes.classifier_routes import router as classifier_router
    from backend.routes.onboarding_routes import router as onboarding_router
    from backend.routes.conflict_routes import router as conflict_router
    print('✅ Routers import OK')"

    ✅ ModelConfig loaded from backend.config
    ✅ Routers import OK
```

### main.py import
```bash
# 3. main.py import
    python -c "from backend.main import app
    print('✅ Main app import OK')"

    ✅ ModelConfig loaded from backend.config
    INFO:backend.main:✅ api_router 등록 완료
    INFO:backend.main:✅ classifier_router 등록 완료
    INFO:backend.main:✅ onboarding_router 등록 완료
    INFO:backend.main:✅ conflict_router 등록 완료
    ✅ Main app import OK
```

---

## `endpoint` 확인하기

### backend/main.py
```python

# prefix들이 잘 붙어있음을 확인할 수 있음

# classifier_router
app.include_router(classifier_router, prefix="/classifier", tags=["classifier"])
logger.info("✅ classifier_router 등록 완료")

# onboarding_router
app.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
logger.info("✅ onboarding_router 등록 완료")

# conflict_router
app.include_router(conflict_router, prefix="/conflict", tags=["conflict"])
logger.info("✅ conflict_router 등록 완료")
```


### classifier_routes.py
```bash

# cat backend/routes/classifier_routes.py | grep -E "@router\.(get|post|put|delete)"

@router.post("/classify", response_model=ClassifyResponse, tags=["Classification", "Main API", "Text"])
@router.post("/file", response_model=ClassifyResponse, tags=["Classification", "Main API", "File Upload"])
@router.post("/advanced/file", tags=["Classification", "Advanced", "LangGraph"])
@router.post("/save-classification", response_model=SuccessResponse, tags=["Classification", "Storage", "Save"])
@router.get("/saved-files", tags=["Classification", "Storage", "List"])
@router.get("/metadata/{file_id}", response_model=Dict, tags=["Classification", "Metadata", "Query"])
@router.post("/text", tags=["Classification", "Advanced", "LangChain Only"])
@router.post("/metadata", response_model=ClassifyResponse, tags=["Classification", "Advanced", "Metadata Based"])
@router.post("/hybrid", response_model=ClassifyResponse, tags=["Classification", "Advanced", "Hybrid"])
@router.post("/parallel", tags=["Classification", "Advanced", "Parallel"])
@router.post("/para", tags=["Classification", "Specialized", "PARA"])
@router.post("/keywords", tags=["Classification", "Specialized", "Keywords"])
@router.get("snapshots", tags=["Classification", "History", "Query"])

```

* 실제 `URL` 주소들

```
    @router.post("/classify", ...)        → 실제 URL: /classifier/classify
    @router.post("/file", ...)            → 실제 URL: /classifier/file
    @router.post("/advanced/file", ...)   → 실제 URL: /classifier/advanced/file
    @router.get("/snapshots", ...)        → 실제 URL: /classifier/snapshots
```

### conflict_routes.py
```bash
# cat backend/routes/conflict_routes.py | grep -E "@router\.(get|post|put|delete)"

@router.post("/classify", response_model=ClassifyResponse)
@router.post("/resolve")

```

### onboarding_routes.py

```bash
# cat backend/routes/onboarding_routes.py | grep -E "@router\.(get|post|put|delete)"

@router.post("/step1", response_model=dict)
@router.get("/suggest-areas")
@router.post("/save-context")
@router.get("/status/{user_id}", response_model=dict)
@router.post("/step2")
@router.post("/step3")
@router.post("/step4")

```

---

## 터미널 `curl` 테스트 결과 

> `classifier_routes.py` 라우터 순서대로 터미널에서 `curl` 테스트 진행

### 메인 텍스트 분류

```bash
# 1. 메인 텍스트 분류
# ✗ curl -X POST http://localhost:8000/classifier/classify \
#  -H "Content-Type: application/json" \
#  -d '{
#    "text": "내일까지 FastAPI 백엔드 리팩터링 완료하고, LangChain 에이전트 연결하기",
#    "user_id": "user_123",
#    "occupation": "소프트웨어 엔지니어",
#    "areas": ["백엔드", "AI", "생산성"],
#    "interests": ["PARA 방법론", "노션", "자동화"]
#  }' | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  2980  100  2682  100   298    147     16  0:00:18  0:00:18 --:--:--   679

{
  "category": "Resources",
  "confidence": 0.8,
  "keyword_tags": [
    "백엔드",
    "AI",
    "생산성",
    "자동화",
    "노션"
  ],
  "reasoning": "",
  "snapshot_id": "Snapshot(id='snap_20251120_012951_628158', timestamp=datetime.datetime(2025, 11, 20, 1, 29, 51, 628175), text='내일까지 FastAPI 백엔드 리팩터링 완료하고, LangChain 에이전트 연결하기', para_result={'category': 'Resources', 'confidence': 0.8, 'reasoning': '사용자 맥락(개발)과 관련된 정보는 없지만, API 설정 방법에 대한 가이드 성격이 강해 Resources로 분류. 사용자 책임 영역과는 관련이 없음.', 'detected_cues': [], 'source': 'langchain', 'has_metadata': True}, keyword_result={'tags': ['기타'], 'confidence': 0.0, 'matched_keywords': {'Projects': [], 'Areas': [], 'Resources': [], 'Archives': []}, 'reasoning': '사용자 맥락이 없고, 입력된 내용이 없어서 키워드 추출이 불가능합니다.', 'para_hints': {'Projects': [], 'Areas': [], 'Resources': [], 'Archives': []}, 'actionability': 'none', 'relevance': 'none', 'user_context_matched': False, 'context_keywords': [], 'context_boost_applied': 0.0, 'user_areas': [], 'processing_time': '5.21s', 'instance_id': '6c95d520'}, conflict_result={'final_category': 'Resources', 'para_category': 'Resources', 'keyword_tags': ['기타'], 'confidence': 0.8, 'confidence_gap': 0.8, 'conflict_detected': False, 'resolution_method': 'auto_by_confidence', 'requires_review': False, 'winner_source': 'para', 'para_reasoning': '사용자 맥락(개발)과 관련된 정보는 없지만, API 설정 방법에 대한 가이드 성격이 강해 Resources로 분류. 사용자 책임 영역과는 관련이 없음.', 'reason': '명확한 승자 선택됨 (Gap: 0.80)'}, metadata={'confidence': 0, 'is_conflict': False, 'final_category': 'Resources'})",
  "conflict_detected": false,
  "requires_review": false,
  "user_context_matched": true,
  "user_areas": [
    "백엔드",
    "AI",
    "생산성"
  ],
  "user_context": {
    "user_id": "user_123",
    "file_id": null,
    "occupation": "소프트웨어 엔지니어",
    "areas": [
      "백엔드",
      "AI",
      "생산성"
    ],
    "interests": [
      "PARA 방법론",
      "노션",
      "자동화"
    ],
    "context_keywords": {
      "백엔드": [
        "백엔드",
        "백엔드 관련",
        "백엔드 업무",
        "백엔드 프로젝트"
      ],
      "AI": [
        "AI",
        "AI 관련",
        "AI 업무",
        "AI 프로젝트"
      ],
      "생산성": [
        "생산성",
        "생산성 관련",
        "생산성 업무",
        "생산성 프로젝트"
      ]
    }
  },
  "context_injected": true,
  "log_info": {
    "csv_log": "/Users/***/***/flownote-mvp/data/classifications/classification_log.csv",
    "json_log": "classification_20251120_012959_814.json",
    "context_saved": true,
    "log_directory": "/Users/***/***/flownote-mvp/data/log"
  },
  "csv_log_result": {
    "status": "success"
  }
}

# Server
INFO:backend.routes.classifier_routes:📝 분류 요청 시작:
INFO:backend.routes.classifier_routes:   - Text: 내일까지 FastAPI 백엔드 리팩터링 완료하고, LangChain 에이전트 연결하기...
INFO:backend.routes.classifier_routes:   - User ID: user_123
INFO:backend.routes.classifier_routes:   - Occupation: 소프트웨어 엔지니어
INFO:backend.routes.classifier_routes:   - Areas: ['백엔드', 'AI', '생산성']
INFO:backend.routes.classifier_routes:   - Areas: ['백엔드', 'AI', '생산성']
INFO:backend.routes.classifier_routes:   - Interests: ['PARA 방법론', '노션', '자동화']
INFO:backend.routes.classifier_routes:✅ 사용자 컨텍스트 생성:
INFO:backend.routes.classifier_routes:   - Occupation: 소프트웨어 엔지니어
INFO:backend.routes.classifier_routes:   - Areas: ['백엔드', 'AI', '생산성']
INFO:backend.routes.classifier_routes:   - Context Keywords: ['백엔드', 'AI', '생산성']
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.langchain_integration:분류 완료: Resources (confidence: 80.00%, metadata: True)
INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier LLM 초기화 성공
INFO:backend.classifier.keyword_classifier:[6c95d520] ✅ Chain 생성 성공 (프롬프트 파일 로드 완료)
INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier initialized (ID: 6c95d520, Time: 01:29:46)
INFO:backend.classifier.keyword_classifier:🔍 [6c95d520] CLASSIFY 시작: text_len=47, has_context=False
INFO:backend.classifier.keyword_classifier:[6c95d520] 🔍 Calling LLM (sync)...
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.keyword_classifier:[6c95d520] ✅ 분류 완료 (sync):
INFO:backend.classifier.keyword_classifier:[6c95d520]   - Tags: ['기타']
INFO:backend.classifier.conflict_resolver:ConflictResolver initialized (threshold: 0.2)
INFO:backend.classifier.conflict_resolver:Resolved: Resources (conflict: False, review: False)
INFO:backend.routes.classifier_routes:✅ PARA 분류 완료:
INFO:backend.routes.classifier_routes:   - Category: Resources
INFO:backend.routes.classifier_routes:   - Confidence: 0.8
INFO:backend.routes.classifier_routes:   - Snapshot ID: Snapshot(id='snap_20251120_012951_628158', timestamp=datetime.datetime(2025, 11, 20, 1, 29, 51, 628175), text='내일까지 FastAPI 백엔드 리팩터링 완료하고, LangChain 에이전트 연결하기', para_result={'category': 'Resources', 'confidence': 0.8, 'reasoning': '사용자 맥락(개발)과 관련된 정보는 없지만, API 설정 방법에 대한 가이드 성격이 강해 Resources로 분류. 사용자 책임 영역과는 관련이 없음.', 'detected_cues': [], 'source': 'langchain', 'has_metadata': True}, keyword_result={'tags': ['기타'], 'confidence': 0.0, 'matched_keywords': {'Projects': [], 'Areas': [], 'Resources': [], 'Archives': []}, 'reasoning': '사용자 맥락이 없고, 입력된 내용이 없어서 키워드 추출이 불가능합니다.', 'para_hints': {'Projects': [], 'Areas': [], 'Resources': [], 'Archives': []}, 'actionability': 'none', 'relevance': 'none', 'user_context_matched': False, 'context_keywords': [], 'context_boost_applied': 0.0, 'user_areas': [], 'processing_time': '5.21s', 'instance_id': '6c95d520'}, conflict_result={'final_category': 'Resources', 'para_category': 'Resources', 'keyword_tags': ['기타'], 'confidence': 0.8, 'confidence_gap': 0.8, 'conflict_detected': False, 'resolution_method': 'auto_by_confidence', 'requires_review': False, 'winner_source': 'para', 'para_reasoning': '사용자 맥락(개발)과 관련된 정보는 없지만, API 설정 방법에 대한 가이드 성격이 강해 Resources로 분류. 사용자 책임 영역과는 관련이 없음.', 'reason': '명확한 승자 선택됨 (Gap: 0.80)'}, metadata={'confidence': 0, 'is_conflict': False, 'final_category': 'Resources'})
INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier LLM 초기화 성공
INFO:backend.classifier.keyword_classifier:[80e3eb5b] ✅ Chain 생성 성공 (프롬프트 파일 로드 완료)
INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier initialized (ID: 80e3eb5b, Time: 01:29:51)
INFO:backend.routes.classifier_routes:🔍 키워드 분류 시작 (Instance ID: 80e3eb5b)
INFO:backend.classifier.keyword_classifier:[80e3eb5b] 🔍 Calling LLM (async)...
INFO:backend.classifier.keyword_classifier:[80e3eb5b]   - Text length: 47
INFO:backend.classifier.keyword_classifier:[80e3eb5b]   - Occupation: 소프트웨어 엔지니어
INFO:backend.classifier.keyword_classifier:[80e3eb5b]   - Areas: 백엔드, AI, 생산성
INFO:backend.classifier.keyword_classifier:[80e3eb5b]   - Context Keywords: 생산성, 백엔드, 자동화, PARA 방법론, 노션, AI
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.keyword_classifier:[80e3eb5b] 📦 RAW LLM Response:
INFO:backend.classifier.keyword_classifier:[80e3eb5b]   - Type: <class 'str'>
INFO:backend.classifier.keyword_classifier:[80e3eb5b]   - Content preview: ```json
{
  "tags": ["백엔드", "AI", "생산성", "자동화", "노션"],
  "confidence": 0.9,
  "matched_keywords": {
    "Projects": [],
    "Areas": ["생산성", "자동화", "백엔드", "AI"],
    "Resources": [],
    "Archives": [
INFO:backend.classifier.keyword_classifier:[80e3eb5b] 📦 Extracted tags: ['백엔드', 'AI', '생산성', '자동화', '노션'] (type: <class 'list'>)
INFO:backend.classifier.keyword_classifier:[80e3eb5b] ✅ 리스트 검증 완료: 5개
INFO:backend.classifier.keyword_classifier:[80e3eb5b] ✅ 분류 완료 (async):
INFO:backend.classifier.keyword_classifier:[80e3eb5b]   - Tags: ['백엔드', 'AI', '생산성', '자동화', '노션']
INFO:backend.classifier.keyword_classifier:[80e3eb5b]   - Confidence: 0.9
INFO:backend.classifier.keyword_classifier:[80e3eb5b]   - Time: 8.18s
INFO:backend.routes.classifier_routes:✅ 키워드 분류 완료:
INFO:backend.routes.classifier_routes:   - Instance ID: 80e3eb5b
INFO:backend.routes.classifier_routes:   - Tags: ['백엔드', 'AI', '생산성', '자동화', '노션']
INFO:backend.routes.classifier_routes:   - Confidence: 0.9
INFO:backend.routes.classifier_routes:   - User Context Matched: True
INFO:backend.routes.classifier_routes:   - Processing Time: 8.18s
INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier LLM 초기화 성공
INFO:backend.classifier.keyword_classifier:[b31fd4dd] ✅ Chain 생성 성공 (프롬프트 파일 로드 완료)
INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier initialized (ID: b31fd4dd, Time: 01:29:59)
INFO:backend.services.conflict_service:✅ ConflictService 초기화 완료
INFO:backend.services.conflict_service:📝 통합 분류 시작: 내일까지 FastAPI 백엔드 리팩터링 완료하고, LangChain 에이전트 연결하기...
INFO:backend.services.conflict_service:3. Conflict Resolution 실행...
INFO:backend.classifier.conflict_resolver:ConflictResolver initialized (threshold: 0.2)
INFO:backend.classifier.conflict_resolver:Resolved: Resources (conflict: True, review: True)
INFO:backend.services.conflict_service:4. Snapshot 저장...
INFO:backend.services.conflict_service:✅ 통합 분류 완료! Snapshot: snap_20251120_012959_813574
INFO:backend.routes.classifier_routes:✅ 충돌 해결 완료:
INFO:backend.routes.classifier_routes:   - Final Category: None
INFO:backend.routes.classifier_routes:   - Keyword Tags: ['백엔드', 'AI', '생산성', '자동화', '노션']
INFO:backend.routes.classifier_routes:   - Conflict Detected: None
INFO:backend.routes.classifier_routes:   - Requires Review: None
✅ [CSV LOG] classification_log.csv 기록 완료: text_input
INFO:backend.routes.classifier_routes:✅ 전체 분류 완료 → Resources | 키워드 5개
INFO:backend.routes.classifier_routes:   - Final Category: Resources
INFO:backend.routes.classifier_routes:   - Keyword Tags: ['백엔드', 'AI', '생산성']...
INFO:backend.routes.classifier_routes:   - User Context Matched: True
INFO:backend.routes.classifier_routes:   - Total Time: ~8.18s
INFO:     127.0.0.1:60076 - "POST /classifier/classify HTTP/1.1" 200 OK
```

### 메인 파일 업로드 분류 
```bash

# 2. 메인 파일 업로드 분류
# curl
# curl -X POST http://localhost:8000/classifier/file \
#  -F "file=@./sample.md" \
#  -F "user_id=user_123" \
#  -F "occupation=소프트웨어 엔지니어" \
#  -F 'areas=["백엔드","AI"]' \
#  -F 'interests=["LangChain","생산성"]' | jq
#curl: (26) Failed to open/read local data from file/application

# Server
INFO:backend.routes.classifier_routes:✅ 키워드 분류 완료:
INFO:backend.routes.classifier_routes:   - Instance ID: 80e3eb5b
INFO:backend.routes.classifier_routes:   - Tags: ['백엔드', 'AI', '생산성', '자동화', '노션']
INFO:backend.routes.classifier_routes:   - Confidence: 0.9
INFO:backend.routes.classifier_routes:   - User Context Matched: True
INFO:backend.routes.classifier_routes:   - Processing Time: 8.18s
INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier LLM 초기화 성공
INFO:backend.classifier.keyword_classifier:[b31fd4dd] ✅ Chain 생성 성공 (프롬프트 파일 로드 완료)
INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier initialized (ID: b31fd4dd, Time: 01:29:59)
INFO:backend.services.conflict_service:✅ ConflictService 초기화 완료
INFO:backend.services.conflict_service:📝 통합 분류 시작: 내일까지 FastAPI 백엔드 리팩터링 완료하고, LangChain 에이전트 연결하기...
INFO:backend.services.conflict_service:3. Conflict Resolution 실행...
INFO:backend.classifier.conflict_resolver:ConflictResolver initialized (threshold: 0.2)
INFO:backend.classifier.conflict_resolver:Resolved: Resources (conflict: True, review: True)
INFO:backend.services.conflict_service:4. Snapshot 저장...
INFO:backend.services.conflict_service:✅ 통합 분류 완료! Snapshot: snap_20251120_012959_813574
INFO:backend.routes.classifier_routes:✅ 충돌 해결 완료:
INFO:backend.routes.classifier_routes:   - Final Category: None
INFO:backend.routes.classifier_routes:   - Keyword Tags: ['백엔드', 'AI', '생산성', '자동화', '노션']
INFO:backend.routes.classifier_routes:   - Conflict Detected: None
INFO:backend.routes.classifier_routes:   - Requires Review: None
✅ [CSV LOG] classification_log.csv 기록 완료: text_input
INFO:backend.routes.classifier_routes:✅ 전체 분류 완료 → Resources | 키워드 5개
INFO:backend.routes.classifier_routes:   - Final Category: Resources
INFO:backend.routes.classifier_routes:   - Keyword Tags: ['백엔드', 'AI', '생산성']...
INFO:backend.routes.classifier_routes:   - User Context Matched: True
INFO:backend.routes.classifier_routes:   - Total Time: ~8.18s
INFO:     127.0.0.1:60076 - "POST /classifier/classify HTTP/1.1" 200 OK
```

### 고급 파일 분류 (LangGraph 기반)
```bash
# 3. 고급 파일 분류 (LangGraph 기반)
#curl -X POST http://localhost:8000/classifier/advanced/file \
#  -F "file=@./long_document.pdf" | jq
curl: (26) Failed to open/read local data from file/application

# Server
# 반응 없음
```

### 저장된 분류 결과 확인 (메모리 저장)
```bash
# 4. 저장된 분류 결과 확인 (메모리 저장)
# curl
#curl http://localhost:8000/classifier/saved-files | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100     2  100     2    0     0    402      0 --:--:-- --:--:-- --:--:--   500
{}

# Server
INFO:     127.0.0.1:60235 - "GET /classifier/saved-files HTTP/1.1" 200 OK
```

### 고급 / 특수 분류 엔드포인트들

#### LangChain 순수 텍스트 분류

```bash
# 5-1. LangChain 순수 텍스트 분류
# curl
# curl -X POST http://localhost:8000/classifier/text \
#  -H "Content-Type: application/json" \
#  -d '{
#    "text": "AWS Lambda로 서버리스 배포하기",
#    "user_id": "user_123"
#  }' | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   564  100   478  100    86     69     12  0:00:07  0:00:06  0:00:01   130

{
  "category": "Projects",
  "confidence": 0.95,
  "keyword_tags": [],
  "reasoning": "명확한 마감일(2025-12-31)과 구체적 실행 단계 존재. 사용자 책임 영역('코드 품질 관리')과 관련 있고 deadline도 있어 Projects로 분류.",
  "snapshot_id": "",
  "conflict_detected": false,
  "requires_review": false,
  "user_context_matched": true,
  "user_areas": [
    "백엔드",
    "AI",
    "생산성"
  ],
  "user_context": {},
  "context_injected": true,
  "log_info": {
    "source": "metadata"
  },
  "csv_log_result": {}


# Server
INFO:backend.routes.classifier_routes:━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFO:backend.routes.classifier_routes:📄 새 분류 요청
INFO:backend.routes.classifier_routes:User ID: user_123
INFO:backend.routes.classifier_routes:User Areas: ['백엔드', 'AI', '생산성']
INFO:backend.routes.classifier_routes:Text Preview: AWS Lambda로 서버리스 배포하기...
INFO:backend.routes.classifier_routes:━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 95.00%, metadata: False)
INFO:backend.routes.classifier_routes:✅ 분류 완료:
INFO:backend.routes.classifier_routes:  - Category: Projects
INFO:backend.routes.classifier_routes:  - Tags: []
INFO:backend.routes.classifier_routes:  - Context Injected: True
INFO:backend.routes.classifier_routes:━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFO:     127.0.0.1:60840 - "POST /classifier/text HTTP/1.1" 200 OK

```

#### 메타데이터 기반 분류
```bash
# 5-2. 메타데이터 기반 분류
# curl
# curl -X POST http://localhost:8000/classifier/metadata \
#  -H "Content-Type: application/json" \
#  -d '{
#    "metadata": {"filename": "회의록_2025.md", "author": "김팀장", "project": "플로우노트"},
#    "user_id": "user_123"
#  }' | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   533  100   398  100   135     54     18  0:00:07  0:00:07 --:--:--    98

{
  "category": "Projects",
  "confidence": 0.92,
  "keyword_tags": [],
  "reasoning": "명확한 deadline(1개월 내), 진행 중 상태, 팀 구성, 사용자 책임 영역 매칭으로 Projects 분류",
  "snapshot_id": "",
  "conflict_detected": false,
  "requires_review": false,
  "user_context_matched": false,
  "user_areas": [],
  "user_context": {},
  "context_injected": false,
  "log_info": {
    "source": "metadata"
  },
  "csv_log_result": {}

# Server
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Projects (confidence: 92.00%)
INFO:     127.0.0.1:60879 - "POST /classifier/metadata HTTP/1.1" 200 OK

```

#### 하이브리드 분류 (텍스트 + 메타데이터)
```bash
# 5-3. 하이브리드 분류 (텍스트 + 메타데이터)
# curl
# curl -X POST http://localhost:8000/classifier/hybrid \
#  -H "Content-Type: application/json" \
#  -d '{
#    "text": "고객사와 다음 주 데모 일정 조율",
#    "metadata": {"filename": "고객미팅노트.txt", "client": "ABC사"},
#    "user_id": "user_123"
#  }' | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   800  100   633  100   167     42     11  0:00:15  0:00:14  0:00:01   172

{
  "category": "Areas",
  "confidence": 0.906,
  "keyword_tags": [],
  "reasoning": "텍스트: 사용자 책임 영역('기술 역량 개발')과 강하게 매칭. API 설정은 개발자의 지속적 기술 역량에 속함. 구체적인 행동 단계는 없지만, 사용자 맥락 우선으로 Areas 분류. | 메타: 명확한 deadline(1개월 내), 진행 중 상태, 팀 구성, 사용자 책임 영역 매칭으로 Projects 분류",
  "snapshot_id": "",
  "conflict_detected": false,
  "requires_review": false,
  "user_context_matched": false,
  "user_areas": [],
  "user_context": {},
  "context_injected": false,
  "log_info": {
    "source": "metadata"
  },
  "csv_log_result": {}


# Server
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.langchain_integration:분류 완료: Areas (confidence: 90.00%, metadata: False)
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Projects (confidence: 92.00%)
INFO:backend.classifier.langchain_integration:하이브리드 분류: Areas (strategy: text_dominant (0.7:0.3), confidence: 90.60%)
INFO:     127.0.0.1:60890 - "POST /classifier/hybrid HTTP/1.1" 200 OK

```

#### 병렬 분류
```bash
# 5-4. 병렬 분류
# curl -X POST http://localhost:8000/classifier/parallel \
#  -H "Content-Type: application/json" \
#  -d '{
#    "text": "React + FastAPI로 MVP 완성하기",
#    "metadata": {"project": "FlowNote", "deadline": "2025-01-15"}
#  }' | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   404  100   282  100   122     38     16  0:00:07  0:00:07 --:--:--    67

{
  "category": "Resources",
  "confidence": 0.0,
  "keyword_tags": [],
  "reasoning": "",
  "snapshot_id": "",
  "conflict_detected": false,
  "requires_review": false,
  "user_context_matched": false,
  "user_areas": [],
  "user_context": {},
  "context_injected": false,
  "log_info": {
    "source": "metadata"
  },
  "csv_log_result": {}


# Server
INFO:     127.0.0.1:60917 - "POST /classifier/parallel HTTP/1.1" 200 OK
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 95.00%, metadata: False)
INFO:     127.0.0.1:60931 - "POST /classifier/para HTTP/1.1" 200 OK

```

#### PARA 전용 분류
```bash
# 5-5. PARA 전용 분류

# curl
# curl -X POST http://localhost:8000/classifier/para \
#  -H "Content-Type: application/json" \
#  -d '{
#    "text": "노션 템플릿 정리해두기",
#    "user_id": "user_123"
#  }' | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   540  100   461  100    79     61     10  0:00:07  0:00:07 --:--:--   106

{
  "category": "Projects",
  "confidence": 0.95,
  "keyword_tags": [],
  "reasoning": "명확한 마감일(2025-12-31)과 구체적 실행 단계가 존재. 사용자 책임 영역('코드 품질 관리')과 관련이 있으며 deadline도 있어 Projects로 분류.",
  "snapshot_id": "",
  "conflict_detected": false,
  "requires_review": false,
  "user_context_matched": false,
  "user_areas": [],
  "user_context": {},
  "context_injected": false,
  "log_info": {
    "source": "metadata"
  },
  "csv_log_result": {}

# Server
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 95.00%, metadata: False)
INFO:     127.0.0.1:60931 - "POST /classifier/para HTTP/1.1" 200 OK

```

#### 키워드만 추출하는 엔드포인트

```bash
# 5-6. 키워드만 추출하는 엔드포인트
# curl
# curl -X POST http://localhost:8000/classifier/keywords \
#  -H "Content-Type: application/json" \
#  -d '{
#    "text": "GraphRAG와 LangGraph 비교 분석 자료 준비",
#    "user_id": "user_123"
#  }' | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   566  100   470  100    96     64     13  0:00:07  0:00:07 --:--:--   115

{
  "category": "Projects",
  "confidence": 0.95,
  "keyword_tags": [],
  "reasoning": "명확한 마감일과 구체적 실행 단계가 존재하여 Projects로 분류. 사용자 책임 영역과 관련이 있으며, 기한이 설정되어 있어 실행 가능성이 높음.",
  "snapshot_id": "",
  "conflict_detected": false,
  "requires_review": false,
  "user_context_matched": false,
  "user_areas": [],
  "user_context": {},
  "context_injected": false,
  "log_info": {
    "source": "metadata"
  },
  "csv_log_result": {}

# Server
INFO:backend.routes.classifier_routes:🔍 키워드 분류 요청: GraphRAG와 LangGraph 비교 분석 자료 준비...
INFO:httpx:HTTP Request: POST https://***/chat/completions "HTTP/1.1 200 OK"
INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 95.00%, metadata: False)
INFO:     127.0.0.1:60947 - "POST /classifier/keywords HTTP/1.1" 200 OK
```

#### 히스토리 / 스냅샷 조회
```bash
# 6. 히스토리 / 스냅샷 조회
# curl
# curl http://localhost:8000/classifier/snapshots | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100    16  100    16    0     0   1091      0 --:--:-- --:--:-- --:--:--  1142
{
  "snapshots": []
}

# Server
INFO:     127.0.0.1:60964 - "GET /classifier/snapshots HTTP/1.1" 200 OK

```

#### 저장된 분류 결과 강제로 저장 (테스트용)
```bash
# 7. 저장된 분류 결과 강제로 저장 (테스트용)
# curl
# curl -X POST http://localhost:8000/classifier/save-classification \
#  -H "Content-Type: application/json" \
#  -d '{
#    "file_id": "test_001",
#    "classification": {"category": "Projects", "keyword_tags": ["테스트", "MVP"]}
#  }' | jq

  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   256  100   139  100   117  18089  15226 --:--:-- --:--:-- --:--:-- 36571

{
  "status": "saved",
  "message": "분류 결과가 성공적으로 저장되었습니다.",
  "data": null,
  "timestamp": "2025-11-20T03:25:42.739381"
}

# Server
✅ [JSON LOG] 20251120_032542_test_001.json 저장 완료!
INFO:backend.routes.classifier_routes:💾 저장됨: test_001 → data/log/20251120_032542_test_001.json
INFO:     127.0.0.1:62026 - "POST /classifier/save-classification HTTP/1.1" 200 OK

```

---

## 수정된 파일들 

### backend/routes/classifier_routes.py

#### 비동기 함수 전환 
```python

conflict_service = ConflictService()
# conflict_result = conflict_service.classify_text(...)  # ← await 누락!

conflict_result = await conflict_service.classify_text(...)
# classifier_routes.py → classify_text() 함수 안
# classifier_routes.py → classify_file_main() 함수 안
```

#### `ClassifyResponse` 반환 구조 수정
```python

# return ClassifyResponse 사용하는 라우터 수정 
return ClassifyResponse(
            category=result.get("category", "Resources"),
            confidence=result.get("confidence", 0.0),
            keyword_tags=result.get("tags", []),
            reasoning=result.get("reasoning", ""),
            snapshot_id="",  # 메타데이터 분류는 스냅샷 없음
            conflict_detected=False,
            requires_review=False,
            user_context_matched=result.get("context_injected", False),
            user_areas=result.get("user_areas", []),
            user_context={},  # 필요하면 채우기
            context_injected=result.get("context_injected", False),
            log_info={"source": "metadata"},
            csv_log_result={}
            )

# /text, /hybrid, /parellel, /para, /keyword → 엔드포인트를 가진 라우터도 모두 수정

```

```python

@router.post("/save-classification")
async def save_classification(request: SaveClassificationRequest):
    try:
        # 최고의 함수 사용!
        saved_path = data_manager.save_json_log()

# backend/data_manager.py
# def save_json_log 함수에서 self args 1개가 부족하다는 오류 메시지 → 해당 함수 수정 (아래에서 확인)


```

### `backend/routes/conflict_routes.py` + `backend/routes/onboarding_routes.py`

```Python

# backend.main.py

# prefix 등록
# classifier_router
app.include_router(classifier_router, prefix="/classifier", tags=["classifier"])
logger.info("✅ classifier_router 등록 완료")

# onboarding_router
app.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
logger.info("✅ onboarding_router 등록 완료")

# conflict_router
app.include_router(conflict_router, prefix="/conflict", tags=["conflict"])
logger.info("✅ conflict_router 등록 완료")

```

```python

# backend/routes/conflict_routes.py
# backend/routes/onboarding_routes.py

# API Router 초기화 ← prefix 없이
router = APIRouter()

```


### backend/data_manager.py

```python
# 기존 (문제 있는 코드)
def save_json_log(
    self,                  # ← 이 self 삭제하기
    user_id: str,
    # ...
)

# → 이렇게 수정 
def save_json_log(         # ← self 완전 삭제
    user_id: str,
    file_name: str,
    category: str,
    confidence: float = 0.0,
    keyword_tags: List[str] = None,
    reasoning: str = "",
    metadata: dict = None,
    source: str = "manual"
):

```

# 🎯 FlowNote - AI 기반 문서 자동 분류 시스템

> **"당신의 문서를 AI가 자동으로 분류합니다"**  
> PARA 방식으로 스마트하게 정리하는 개인 지식 관리 시스템

---

## 1️⃣ 프로젝트 개요 (Why)

### 📌 배경 및 문제 인식

현대인들은 매일 수많은 문서, 메모, 자료를 생성하고 저장합니다. 하지만 이렇게 쌓인 정보들을 효과적으로 분류하고 관리하는 것은 쉽지 않습니다.

**주요 문제점:**
- 📁 **분류 기준의 모호함**: "이 자료는 프로젝트일까, 참고 자료일까?"
- ⏰ **시간 낭비**: 수동 분류에 많은 시간 소요
- 🔍 **검색의 어려움**: 필요할 때 원하는 정보를 찾기 힘듦
- 🤯 **정보 과부하**: 쌓이는 파일만 늘고 정리는 안 됨

### 🎯 해결하고 싶은 문제

**"개인의 맥락을 이해하고, 문서를 자동으로 PARA 방식으로 분류하여 생산성을 높이는 AI 시스템이 필요하다."**

---

## 2️⃣ 핵심 아이디어 (What)

### 💡 서비스/프로젝트 개념

**FlowNote**는 사용자의 직업과 관심 영역을 학습하여, 업로드된 문서를 **PARA 방식**(Projects, Areas, Resources, Archives)으로 자동 분류하는 AI 기반 지식 관리 시스템입니다.

### 🌟 핵심 가치

1. **개인화된 분류 (Personalization)**
   - 사용자의 직업과 관심 영역을 학습
   - 동일한 문서도 사용자에 따라 다르게 분류

2. **PARA 방법론 활용 (Proven Framework)**
   - Tiago Forte의 검증된 정보 관리 시스템
   - 명확한 4가지 카테고리로 정리

3. **AI 자동화 (Automation)**
   - GPT-4o 기반 지능형 분류
   - 신뢰도와 근거를 함께 제공

4. **통합 검색 (Unified Search)**
   - FAISS 벡터 검색 엔진
   - 의미 기반 문서 탐색

### 📊 PARA 방식이란?

```
📋 Projects (프로젝트)
   → 기한이 있는 구체적 목표
   → 예: "11월 30일까지 대시보드 구현"

🎯 Areas (분야)
   → 지속적 책임 영역
   → 예: "팀 성과 관리 지속 업무"

📚 Resources (자료)
   → 참고용 정보/학습 자료
   → 예: "Python 최적화 가이드"

📦 Archives (보관)
   → 완료된 프로젝트 보관
   → 예: "2024년 프로젝트 결과"
```

### 🔍 레퍼런스 분석 및 차별점

| 비교 대상 | 주요 특징 | 한계점 | FlowNote 차별성 |
|-----------|----------|--------|----------------|
| **Notion** | 수동 분류, 다양한 기능 | AI 분류 없음, 수동 작업 필수 | **AI 자동 분류** + 맥락 학습 |
| **Obsidian** | 마크다운 기반, 링크 관리 | 분류 시스템 없음 | **PARA 기반 자동 정리** |
| **Evernote** | 태그 기반 분류 | 지능형 분류 부족 | **GPT-4o 기반 지능형 분류** |
| **Google Drive** | 클라우드 저장 | 분류는 폴더에 의존 | **의미 기반 검색** + 자동 분류 |

**💡 핵심 차별점:**
- **개인 맥락 학습**: 사용자 직업/관심을 이해하고 반영
- **AI 자동 분류**: GPT-4o가 PARA 기준으로 자동 분류
- **신뢰도 제공**: 분류 근거와 신뢰도 점수 표시
- **통합 검색**: 벡터 검색으로 의미 기반 탐색

---

## 3️⃣ 기술 스택 및 구조 (How)

### 🛠️ 사용 기술 스택

#### **Backend (Python 3.11)**
```python
# Core Framework
FastAPI 0.120.4        # REST API 서버
Uvicorn 0.38.0         # ASGI 서버

# AI & LLM
LangChain 1.0.2        # AI 체인 관리
OpenAI API             # GPT-4o, GPT-4o-mini

# Search & Embeddings
FAISS 1.12.0           # 벡터 검색 엔진
tiktoken 0.12.0        # 토큰 계산

# Data Processing
pdfplumber 0.11.0      # PDF 파싱
pandas 2.3.3           # 데이터 처리
```

#### **Frontend**
```python
Streamlit 1.51.0       # 웹 UI 프레임워크
Plotly 6.3.1           # 데이터 시각화
st-aggrid 1.1.9        # 테이블 렌더링
```

#### **Database & Storage**
```python
SQLite 3               # 메타데이터 저장
JSON                   # 파일 메타데이터, 컨텍스트 저장
```

### 🏗️ 시스템 아키텍처

```
┌─────────────────────────────────────────┐
│     Frontend (Streamlit)                │
│  ┌───────────────────────────────────┐  │
│  │  Tab 1: 온보딩 (영역 추천)         │  │
│  │  Tab 2: 파일 분류                 │  │
│  │  Tab 3: 키워드 검색               │  │
│  │  Tab 4: 통계 대시보드             │  │
│  │  Tab 5: 메타데이터                │  │
│  └───────────────────────────────────┘  │
└─────────────┬───────────────────────────┘
              │ HTTP POST/GET
              ↓
┌─────────────────────────────────────────┐
│     Backend (FastAPI)                   │
│  ┌───────────────────────────────────┐  │
│  │  /api/onboarding/step1            │  │
│  │  /api/onboarding/suggest-areas    │  │
│  │  /api/onboarding/save-context     │  │
│  │  /api/classifier/file             │  │
│  └───────────────────────────────────┘  │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  Services                         │  │
│  │   • PARAClassifier               │  │
│  │   • EmbeddingGenerator           │  │
│  │   • FAISSRetriever               │  │
│  │   • TextChunker                  │  │
│  └───────────────────────────────────┘  │
└─────────────┬───────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────┐
│  OpenAI API (GPT-4o)                    │
│   • 영역 추천 (10개 생성)                │
│   • PARA 분류 (맥락 반영)                │
│   • 텍스트 임베딩 생성                   │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│  Storage Layer                          │
│   • SQLite (메타데이터)                  │
│   • JSON (파일 정보, 컨텍스트)            │
│   • FAISS Index (벡터 검색)              │
└─────────────────────────────────────────┘
```

### 🔄 핵심 워크플로우

#### **1. 온보딩 플로우**
```python
# Step 1: 사용자 정보 입력
user_data = {
    "name": "Jay",
    "occupation": "개발자"
}

# Step 2: GPT-4o가 10개 영역 추천
prompt = f"""
직업: {occupation}
위 직업에 맞는 관심 영역 10개를 추천해주세요.
"""
suggested_areas = gpt4o.generate(prompt)

# Step 3: 사용자가 5개 선택
selected_areas = user_selects(suggested_areas, count=5)

# Step 4: 컨텍스트 저장
context = {
    "user_id": generate_uuid(),
    "name": name,
    "occupation": occupation,
    "selected_areas": selected_areas
}
save_to_json(context)
```

#### **2. AI 기반 분류 플로우**
```python
# Step 1: 파일 업로드 및 텍스트 추출
text = extract_text_from_file(uploaded_file)

# Step 2: 사용자 컨텍스트 로드
user_context = load_user_context(user_id)

# Step 3: LangChain + GPT-4o 분류
prompt = f"""
사용자 정보:
- 직업: {user_context['occupation']}
- 관심 영역: {user_context['selected_areas']}

문서 내용:
{text}

이 문서를 PARA 방식으로 분류하세요.
(Projects/Areas/Resources/Archives)
"""

result = langchain_classifier.run(prompt)

# Step 4: 결과 반환
return {
    "category": result.category,
    "confidence": result.confidence,
    "reasoning": result.reasoning,
    "keywords": result.keywords
}
```

#### **3. 벡터 검색 플로우**
```python
# Step 1: 문서 청킹
chunks = text_chunker.chunk_text(document)

# Step 2: 임베딩 생성
embeddings = openai.embeddings.create(
    model="text-embedding-3-small",
    input=chunks
)

# Step 3: FAISS 인덱스 구축
index = faiss.IndexFlatL2(dimension)
index.add(embeddings)

# Step 4: 검색 실행
query_embedding = openai.embeddings.create(
    model="text-embedding-3-small",
    input=query
)
results = index.search(query_embedding, k=5)
```

### 📂 프로젝트 구조

```
flownote-mvp/
│
├── backend/
│   ├── app.py                    # FastAPI 메인
│   ├── embedding.py              # 임베딩 생성
│   ├── chunking.py               # 텍스트 청킹
│   ├── faiss_search.py           # FAISS 검색
│   ├── classifier/
│   │   ├── para_classifier.py    # 분류 로직
│   │   └── para_agent_wrapper.py # LangChain 통합
│   └── database/
│       ├── connection.py         # DB 연결
│       └── metadata_schema.py    # 스키마
│
├── streamlit/
│   ├── app.py                    # 메인 UI
│   └── pages/
│       └── dashboard.py          # 대시보드
│
├── data/
│   ├── exports/                  # 분류된 파일
│   ├── faiss_indexes/            # 검색 인덱스
│   └── onboarding_contexts.json # 사용자 컨텍스트
│
└── requirements.txt              # 의존성
```

---

## 4️⃣ 주요 기능 (Features)

### 🎯 핵심 기능 3가지

| 기능 | 설명 | 기술 스택 |
|------|------|----------|
| **스마트 온보딩** | GPT-4o가 사용자 직업 분석 → 10개 영역 추천 → 5개 선택 → 맥락 저장 | LangChain + GPT-4o |
| **AI 자동 분류** | 사용자 맥락 반영하여 PARA 방식 자동 분류 + 신뢰도 + 키워드 제공 | GPT-4o + LangChain |
| **벡터 검색** | FAISS 기반 의미 검색 + 유사도 점수 + 마크다운 내보내기 | FAISS + OpenAI Embeddings |

### 🌟 부가 기능

1. **실시간 대시보드**
   - PARA 분포 시각화 (Plotly)
   - 파일 트리 구조 표시
   - 최근 활동 로그

2. **메타데이터 관리**
   - 분류 히스토리 저장
   - 신뢰도 통계
   - 세션별 필터링

3. **검색 히스토리**
   - 모든 검색 기록 자동 저장
   - 이전 검색 재확인

---

## 5️⃣ 사용자 흐름 (User Flow)

```
[사용자 접속]
    ↓
[Tab 1: 온보딩]
    → 이름, 직업 입력
    → GPT-4o가 10개 영역 추천
    → 5개 선택
    → 완료 ✅
    ↓
[Tab 2: 파일 분류]
    → PDF/TXT/MD 업로드
    → "분류 시작" 클릭
    → AI 분석 중... (맥락 반영)
    → 결과 확인:
       • 카테고리
       • 신뢰도
       • 키워드
       • 분류 근거
    ↓
[Tab 3: 키워드 검색]
    → 문서 업로드 & 처리
    → 검색어 입력
    → 유사도 기반 결과 확인
    → 마크다운 내보내기
    ↓
[Tab 4: 통계]
    → PARA 분포 확인
    → 분류 히스토리
    ↓
[Tab 5: 메타데이터]
    → 상세 정보 확인
    → DB 전체 데이터
```

---

## 6️⃣ 화면 구성 (UI/UX)

### 📱 주요 화면

#### **1. 온보딩 화면 (Step 1)**
```
┌─────────────────────────────────────┐
│  🚀 온보딩: 기본 정보 입력            │
├─────────────────────────────────────┤
│                                     │
│  이름: [Jay         ]               │
│                                     │
│  직업: [개발자      ]               │
│                                     │
│         [다음 단계 →]               │
│                                     │
└─────────────────────────────────────┘
```

#### **2. 온보딩 화면 (Step 2)**
```
┌─────────────────────────────────────┐
│  🚀 온보딩: 관심 영역 선택 (5개)      │
├─────────────────────────────────────┤
│                                     │
│  GPT-4o 추천 영역:                  │
│  ☑ Python Development              │
│  ☑ Machine Learning                │
│  ☐ Web Development                 │
│  ☑ Data Science                    │
│  ☐ DevOps                          │
│  ☑ Cloud Computing                 │
│  ☐ Mobile Development              │
│  ☑ Database Management             │
│  ☐ Cybersecurity                   │
│  ☐ UI/UX Design                    │
│                                     │
│  선택: 5/5 ✅                       │
│                                     │
│  [← 이전]  [완료 →]                │
│                                     │
└─────────────────────────────────────┘
```

#### **3. 파일 분류 화면**
```
┌─────────────────────────────────────┐
│  📤 파일 업로드 & 자동 분류           │
├─────────────────────────────────────┤
│                                     │
│  📄 파일 정보                        │
│  • 파일명: project_proposal.pdf    │
│  • 크기: 2.5 MB                     │
│  • 타입: PDF                        │
│                                     │
│       [🚀 분류 시작]                │
│                                     │
├─────────────────────────────────────┤
│  ✅ 분류 완료!                       │
│                                     │
│  📊 분류 결과                        │
│  • 카테고리: 📋 Projects           │
│  • 신뢰도: 95%                      │
│  • 맥락 반영: ✅                    │
│  • 키워드: 프로젝트, 마감일, 목표   │
│                                     │
│  📝 분류 근거:                       │
│  "마감일(11월 30일)과 구체적 목표가  │
│   명시되어 있어 Projects로 분류"    │
│                                     │
└─────────────────────────────────────┘
```

#### **4. 대시보드 화면**
```
┌─────────────────────────────────────┐
│  📊 FlowNote Dashboard              │
├─────────────────────────────────────┤
│                                     │
│  📁 전체 파일   🔍 총 검색          │
│     42개           156회           │
│    ▲ +12         ▲ +23%           │
│                                     │
│  📊 분류율     ⭐ 평균 신뢰도       │
│    85.7%          0.89             │
│    ▲ +5.0%      ▲ +0.05           │
│                                     │
├─────────────────────────────────────┤
│  📈 PARA 분포                        │
│                                     │
│  Projects   ████████ 15개          │
│  Areas      ██████ 10개            │
│  Resources  ████████████ 20개      │
│  Archives   ████ 7개               │
│                                     │
└─────────────────────────────────────┘
```

---

## 7️⃣ 예상 결과 및 기대효과 (Impact)

### 🎯 핵심 성과

1. **생산성 향상**
   - 문서 분류 시간 **80% 감소** (수동 5분 → 자동 1분)
   - 검색 정확도 **40% 향상** (키워드 검색 → 의미 기반 검색)

2. **개인화된 경험**
   - 사용자 맥락 반영으로 **분류 정확도 25% 향상**
   - 직업별 맞춤 영역 추천

3. **지식 관리 체계화**
   - PARA 방식으로 **명확한 4단계 분류**
   - 프로젝트 완료 → 자동 Archives 이동 (예정)

### 📊 정량적 효과

| 지표 | 목표 | 현재 |
|------|------|------|
| 분류 정확도 | 90%+ | 85%+ |
| 평균 신뢰도 | 0.85+ | 0.89 |
| 검색 응답 시간 | <1초 | 0.3초 |
| 사용자 만족도 | 4.5/5.0 | 측정 예정 |

### 🌟 정성적 효과

- **인지 부하 감소**: "어디에 저장할까?" 고민 불필요
- **검색 경험 개선**: 의미 기반 검색으로 직관적
- **일관된 정리**: PARA 방식으로 체계적 관리

---

## 8️⃣ 기술적 도전과 해결 과제

### 🚧 마주친 기술적 어려움

#### **1. LangChain 프롬프트 이스케이프 문제**

**문제:**
```python
# PromptTemplate에서 중괄호 {} 오류 발생
prompt = PromptTemplate.from_template("""
PARA 분류:
- Projects: {마감일 있음}  # ❌ 오류!
""")
```

**해결:**
```python
# 이중 중괄호 {{}} 사용
prompt = PromptTemplate.from_template("""
PARA 분류:
- Projects: {{마감일 있음}}  # ✅ 정상!
""")
```

#### **2. 사용자 맥락 반영 분류**

**문제:**
- 동일한 문서도 사용자에 따라 다르게 분류되어야 함
- 맥락 정보를 어떻게 프롬프트에 주입할까?

**해결:**
```python
# 사용자 컨텍스트를 프롬프트에 포함
prompt = f"""
[사용자 맥락]
직업: {occupation}
관심 영역: {', '.join(selected_areas)}

[문서 내용]
{text}

위 맥락을 고려하여 PARA 분류하세요.
"""
```

#### **3. FAISS 인덱스 관리**

**문제:**
- 여러 파일 처리 시 인덱스 병합
- 메타데이터 매칭

**해결:**
```python
# 메타데이터와 함께 저장
retriever.add_documents(
    embeddings=embeddings_array,
    metadata=[
        {"content": chunk, "filename": file.name}
        for chunk in chunks
    ]
)
```

### 💡 개선 및 학습 포인트

1. **LangChain 활용**
   - Prompt Engineering의 중요성 체감
   - 변수 주입 방식 (f-string vs PromptTemplate)

2. **API 비용 최적화**
   - GPT-4o-mini로 경량 작업 분리
   - 캐싱 전략 도입 필요

3. **사용자 경험**
   - 온보딩 단계 추가로 첫 진입 장벽 발생
   - 하지만 맥락 기반 분류 정확도 크게 향상

---

## 9️⃣ 향후 개선 및 확장 방향 (Next Steps)

### 🔜 단기 개선 (v4.0, ~12월)

1. **분류 정확도 개선**
   - Few-shot learning 도입
   - 사용자 피드백 학습

2. **배치 처리 기능**
   - 여러 파일 동시 처리
   - 폴더 단위 업로드

3. **태그 자동 생성**
   - AI가 키워드 태그 생성
   - 태그 클라우드 시각화

### 🚀 중기 확장 (v5.0, ~2026년 Q1)

1. **LangGraph 멀티 스텝 분류**
   - 복잡한 문서는 단계별 분석
   - 신뢰도 낮으면 재분류

2. **외부 도구 연동**
   - Notion 연동 (자동 동기화)
   - Obsidian Export
   - Google Drive 백업

3. **협업 기능**
   - 팀 공유 워크스페이스
   - 권한 관리

### 🌟 장기 비전 (v6.0+)

1. **모바일 앱**
   - iOS/Android 네이티브 앱
   - 사진 → OCR → 자동 분류

2. **에이전트 모드**
   - 주기적으로 자동 정리
   - "이번 달 완료된 프로젝트를 Archives로 이동"

3. **커뮤니티 템플릿**
   - 직업별 추천 템플릿
   - 베스트 프랙티스 공유

---

## 🔟 프로젝트 진행 중 배운 점

### 📚 기술적 학습

1. **LangChain 활용**
   - Prompt Engineering의 핵심: 명확한 지시 + 예시
   - Chain 구성: 단순 호출 vs 복잡한 워크플로우

2. **벡터 검색 (FAISS)**
   - 임베딩 차원 선택의 중요성
   - 인덱스 타입별 성능 차이

3. **FastAPI + Streamlit 통합**
   - REST API 설계 원칙
   - 비동기 처리 고려

### 💡 프로젝트 관리

1. **MVP 우선 원칙**
   - Issue별로 핵심 기능부터 구현
   - 완벽보다는 작동하는 프로토타입

2. **사용자 피드백의 중요성**
   - 온보딩 플로우 개선 (테스트 결과)
   - UI/UX 반복 개선

3. **문서화의 가치**
   - README.md로 명확한 소통
   - 코드 주석으로 유지보수성 확보

---

## 1️⃣1️⃣ 데모 및 실행 방법

### 🚀 빠른 시작

```bash
# 1. 저장소 클론
git clone https://github.com/jjaayy2222/flownote-mvp.git
cd flownote-mvp

# 2. 가상환경 설정
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 패키지 설치
pip install -r requirements.txt

# 4. 환경변수 설정 (.env 파일 생성)
OPENAI_API_KEY=sk-your-api-key-here
GPT4O_API_KEY=sk-your-api-key-here
GPT4O_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small

# 5. Backend 실행
cd backend
python app.py
# → http://127.0.0.1:8000

# 6. Frontend 실행 (새 터미널)
cd streamlit
streamlit run app.py
# → http://localhost:8501
```

### 🎬 데모 영상

* 온보딩 & 자동 분류
  * [온보딩 & 자동 분류](https://www.canva.com/design/DAG4Zw4lO8g/1deKsg8oiREVTAJVgyOv1Q/watch?utm_content=DAG4Zw4lO8g&utm_campaign=designshare&utm_medium=link2&utm_source=uniquelinks&utlId=h2dac626132)

* 키워드 검색
  * [키워드 검색](https://www.canva.com/design/DAG4aOtBiYQ/vit5sPZAekW_K7MP8RqjOA/watch?utm_content=DAG4aOtBiYQ&utm_campaign=designshare&utm_medium=link2&utm_source=uniquelinks&utlId=hac84e4693e)

### 📷 스크린 샷

* 대시보드
  * ![대시보드 1](../../../11_12/screenshots/스크린샷%202025-11-12%2000.45.40.png)
  * ![대시보드 2](../../../11_12/screenshots/스크린샷%202025-11-12%2000.46.17.png)
  * ![대시보드 3](../../../11_12/screenshots/스크린샷%202025-11-12%2000.46.36.png)
  * ![대시보드 4](../../../11_12/screenshots/스크린샷%202025-11-12%2000.46.42.png)
  * ![대시보드 5](../../../11_12/screenshots/스크린샷%202025-11-12%2000.46.49.png)
  * ![대시보드 6](../../../11_12/screenshots/스크린샷%202025-11-12%2000.46.59.png)

---

## 1️⃣2️⃣ 결론

### 🎯 프로젝트 요약

**FlowNote**는 AI 기반 문서 자동 분류 시스템으로, 다음을 달성했습니다:

### 💡 핵심 가치

- **개인화된 분류**: 사용자 직업/관심 영역 학습
- **AI 자동화**: GPT-4o 기반 지능형 분류
- **통합 검색**: FAISS 벡터 검색 엔진
- **실시간 통계**: 대시보드 시각화

---
# 🎯 FlowNote - AI 기반 PARA 분류 시스템

> **당신의 문서를 AI가 자동으로 분류합니다**  
> PARA 방식 (Projects, Areas, Resources, Archives)으로 스마트하게 정리

<br>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/fastapi-latest-green?logo=fastapi&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/streamlit-latest-red?logo=streamlit&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/celery-5.4-green?logo=celery&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/redis-7.x-red?logo=redis&logoColor=white" style="margin: 4px;" />
  <img src="https://img.shields.io/badge/license-MIT-green?logo=opensourceinitiative&logoColor=white" style="margin: 4px;" />
</p>

<br>

<p align="center">
  <img src="https://github.com/jjaayy2222/flownote-mvp/actions/workflows/ci.yml/badge.svg" alt="CI" />
  <img src="https://codecov.io/gh/jjaayy2222/flownote-mvp/branch/main/graph/badge.svg" alt="codecov" />
</p>

<br>

---

## 📖 목차

1. [프로젝트 소개](#1-프로젝트-소개)
2. [핵심 기능](#2-핵심-기능)
3. [기술 스택](#3-기술-스택)
4. [프로젝트 구조](#4-프로젝트-구조)
5. [테스팅](#5-테스팅)
6. [설치 및 실행](#6-설치-및-실행)
7. [사용 방법](#7-사용-방법)
8. [개발 히스토리](#8-개발-히스토리)
9. [로드맵](#9-로드맵)
10. [FAQ](#10-faq)
11. [기여하기](#11-기여하기)
12. [라이선스](#12-라이선스)
13. [개발자](#13-개발자)

---

## 1. 📖 프로젝트 소개

**FlowNote**는 AI 기반 문서 자동 분류 시스템입니다. 사용자의 직업과 관심 영역을 학습하여, 업로드된 문서를 PARA 방식으로 지능적으로 분류합니다.

### 💡 핵심 아이디어

```
    사용자 온보딩 (직업, 관심 영역)
        ↓
    GPT-4o가 사용자 맥락 학습
        ↓
    파일 업로드 (PDF, TXT, MD)
        ↓
    AI가 PARA 방식으로 자동 분류
        ↓
    분류 결과 + 신뢰도 + 키워드 제시
        ↓
    🎉 완료!
```

**예시:**
- **입력**: `"프로젝트 제안서_2025.pdf"`
- **결과**: `📋 Projects` (신뢰도 95%)
- **키워드**: `프로젝트`, `마감일`, `목표`

---

## 2. ✨ 핵심 기능

### 2.1 🚀 **스마트 온보딩**
- GPT-4o가 사용자 직업 분석
- 10개 영역 추천 → 5개 선택
- 사용자 맥락 저장 및 활용

### 2.2 📄 **AI 기반 자동 분류**
```
📋 Projects (프로젝트)
   → 기한/마감일이 있는 구체적 목표
   예: "11월까지 대시보드 구현"

🎯 Areas (분야)
   → 지속적 책임 영역
   예: "팀 성과 관리 지속 업무"

📚 Resources (자료)
   → 참고용 정보/학습 자료
   예: "Python 최적화 가이드"

📦 Archives (보관)
   → 완료된 프로젝트 보관
   예: "2024년 프로젝트 결과"
```

### 2.3 🔍 **키워드 검색 시스템**
- FAISS 벡터 검색 엔진
- OpenAI Embeddings 활용
- 실시간 유사도 점수 표시
- 검색 히스토리 저장

### 2.4 📊 **실시간 대시보드**
- PARA 분류 통계 시각화
- 파일 트리 구조 표시
- 최근 활동 로그
- 메타데이터 관리

### 2.5 🎯 **맥락 기반 분류**
- 사용자 직업/관심 영역 반영
- 신뢰도 점수 (0-100%)
- 키워드 태그 자동 생성
- 분류 근거 설명

### 2.6 🤖 **지능형 자동화 시스템**
- **자동 재분류**: 매일/매주 분류 신뢰도가 낮은 문서를 AI가 재검토
- **스마트 아카이빙**: 장기간(90일 이상) 수정되지 않은 Projects 문서를 Archives로 이동 제안
- **정기 리포트**: 주간/월간 분류 통계 및 인사이트 리포트 생성
- **시스템 모니터링**: 백그라운드 작업 상태 및 동기화 무결성 자동 점검
- **Celery & Redis**: 안정적인 분산 작업 큐 처리

### 2.7 🔗 **MCP 서버 & Obsidian 연동** (v5.0 Phase 1)
- **Model Context Protocol (MCP)**: Claude Desktop과 통합 가능한 MCP 서버 구현
- **Obsidian 동기화**: 실시간 Vault 파일 감지 및 자동 분류
- **충돌 해결**: 3-way 충돌 감지 및 자동 해결 (Rename 전략)
- **MCP Tools**: `classify_content`, `search_notes`, `get_automation_stats`
- **MCP Resources**: PARA 카테고리별 파일 리스트 제공

### 2.8 📊 **Next.js 기반 모던 대시보드** (v5.0 Phase 2-3)
- **Sync Monitor**: Obsidian 연결 상태 및 MCP 서버 상태 실시간 모니터링
- **PARA Graph View**: React Flow 기반 파일-카테고리 관계 시각화
  - 노드 클릭 인터랙션 (Toast 알림)
  - Deterministic Layout (새로고침 시에도 위치 유지)
  - Zoom/Pan 지원
- **Advanced Stats**: Recharts 기반 통계 차트
  - Activity Heatmap (GitHub 스타일 연간 활동)
  - Weekly Trend (12주 파일 처리량)
  - PARA Distribution (카테고리별 비중 Pie Chart)
- **Mobile Responsive**: 데스크탑/모바일 자동 전환 내비게이션
- **Accessibility**: ARIA 속성 및 스크린 리더 지원

---

## 3. 💻 기술 스택

### 3.1 Backend
| 기술 | 버전 | 용도 |
|------|------|------|
| **Python** | 3.11.10 | 개발 언어 |
| **FastAPI** | 0.120.4 | REST API 프레임워크 |
| **LangChain** | 1.0.2 | AI 체인 관리 |
| **Celery** | 5.4.0 | 비동기 작업 큐 & 스케줄링 |
| **Redis** | 7.x | 메시지 브로커 & 캐시 |
| **Flower** | 2.0.1 | Celery 모니터링 대시보드 |
| **SQLite** | 3 | 메타데이터 저장 |
| **Uvicorn** | 0.38.0 | ASGI 서버 |

### 3.2 Frontend
| 기술 | 버전 | 용도 |
|------|------|------|
| **Next.js** | 16.1.1 | React 프레임워크 (App Router) |
| **React** | 19.2.3 | UI 라이브러리 |
| **TypeScript** | 5.x | 타입 안전성 |
| **Tailwind CSS** | 4.x | 스타일링 |
| **Shadcn UI** | latest | UI 컴포넌트 라이브러리 |
| **React Flow** | 11.11.4 | 그래프 시각화 |
| **Recharts** | 3.6.0 | 차트 라이브러리 |
| **Sonner** | 2.0.7 | Toast 알림 |

### 3.3 LLM & AI
| 기술 | 모델 | 용도 |
|------|------|------|
| **OpenAI API** | GPT-4o | PARA 분류, 영역 추천 |
| **OpenAI API** | GPT-4o-mini | 경량 작업 |
| **OpenAI Embeddings** | text-embedding-3-small | 벡터 임베딩 |

### 3.4 검색 & 데이터
| 기술 | 버전 | 용도 |
|------|------|------|
| **FAISS** | 1.12.0 | 벡터 검색 엔진 |
| **pdfplumber** | 0.11.0 | PDF 파싱 |
| **python-dotenv** | 1.1.1 | 환경변수 관리 |

---

## 4. 📁 프로젝트 구조

```bash
flownote-mvp/
│
├── requirements.txt                    # Python 의존성
├── .env.example                        # 환경변수 예시
├── .gitignore
│
├── backend/                            # FastAPI 백엔드
│   ├── main.py                         # FastAPI 메인 앱 (Entrypoint)
│   ├── celery_app/                     # Celery 설정
│   │   ├── celery.py                   # Celery 인스턴스
│   │   ├── config.py                   # Celery 설정
│   │   └── tasks/                      # 비동기 작업들 (재분류, 아카이빙 등)
│   │
│   ├── mcp/                            # MCP 서버 ✨
│   │   ├── server.py                   # MCP 서버 구현
│   │   └── tools/                      # MCP Tools (classify, search 등)
│   │
│   ├── services/                       # 비즈니스 로직 (Service Layer)
│   │   ├── obsidian_sync.py            # Obsidian 동기화 ✨
│   │   ├── conflict_resolution_service.py  # 충돌 해결 ✨
│   │   └── ...
│   │
│   ├── embedding.py                    # 임베딩 생성
│   ├── faiss_search.py                 # FAISS 검색
│   ├── classifier/                     # PARA 분류 로직
│   └── ...
│
├── web_ui/                             # Next.js Frontend ✨
│   ├── src/
│   │   ├── app/                        # App Router
│   │   │   ├── page.tsx                # Dashboard
│   │   │   ├── graph/page.tsx          # Graph View
│   │   │   └── stats/page.tsx          # Statistics
│   │   ├── components/                 # React 컴포넌트
│   │   │   ├── dashboard/              # Dashboard 컴포넌트
│   │   │   ├── para/GraphView.tsx      # Graph View
│   │   │   └── layout/                 # Navigation
│   │   └── config/                     # 설정 파일
│   └── package.json
│
├── data/                               # 데이터 저장소
├── docs/                               # 문서
│   └── P/                              # 프로젝트 페이즈 문서
│       ├── v5_phase1_mcp_server/       # MCP 서버 문서
│       ├── v5_phase2_frontend/         # Frontend 문서
│       └── v5_phase3_visualization/    # Visualization 문서
└── README.md                           # 본 문서
```

---

## 5. 🧪 테스트 및 품질 관리

FlowNote는 엄격한 테스트와 품질 관리를 통해 안정성을 보장합니다.

### 5.1 테스트 실행

```bash
# 전체 테스트 실행
pytest

# 커버리지 리포트 생성
pytest --cov=backend --cov-report=term-missing
```

### 5.2 테스트 커버리지 (Phase 4 기준)

| 모듈 | 커버리지 | 비고 |
|------|----------|------|
| **전체** | **55%** | 주요 로직 위주 테스트 |
| `util.py` (Celery Tasks) | 80%+ | 자동화 태스크 |
| `parallel_processor.py` | 100% | 병렬 처리 |
| `classification_service.py` | 89% | 핵심 로직 |

---

## 6. 🚀 설치 및 실행

### 6.1 사전 요구사항
- **Python**: 3.11+
- **OpenAI API Key**: [platform.openai.com](https://platform.openai.com/)
- **Redis Server**: 6.2+ (Celery 브로커용)

### 6.2 설치 방법

```bash
# 1. 저장소 클론
git clone https://github.com/jjaayy2222/flownote-mvp.git
cd flownote-mvp

# 2. 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate

# 3. Redis 설치 (macOS)
brew install redis
brew services start redis

# 4. 패키지 설치
pip install -r requirements.txt

# 5. 환경변수 설정
cp .env.example .env
# .env 파일에 OpenAI API 키 및 REDIS_URL 설정
```

### 6.3 전체 서비스 실행 가이드

FlowNote의 모든 기능을 사용하려면 **5개의 터미널**이 필요합니다.

**1. FastAPI Backend 실행 (Terminal 1)**
```bash
cd /Users/jay/ICT-projects/flownote-mvp
pyenv activate myenv
python -m uvicorn backend.main:app --reload
# → http://127.0.0.1:8000
```

**2. Next.js Frontend 실행 (Terminal 2)**
```bash
cd web_ui
npm run dev
# → http://localhost:3000
```

**3. Celery Worker & Beat 실행 (Terminal 3)**
```bash
# Worker와 Beat 동시 실행 (개발용)
celery -A backend.celery_app.celery worker --beat --loglevel=info
```

**4. Flower 모니터링 실행 (Terminal 4)**
```bash
celery -A backend.celery_app.celery flower --port=5555
# → http://localhost:5555
```

**5. MCP 서버 실행 (Terminal 5) - Optional**
```bash
# Claude Desktop 연동 시
python -m backend.mcp.server
# 또는 Claude Desktop 설정에서 자동 시작
```

---

## 7. 📖 사용 방법

### 7.1 **Step 1: 온보딩**
1. `Tab 1: 온보딩` 이동
2. 이름과 직업 입력 후 영역 선택

### 7.2 **Step 2: 파일 분류**
1. `Tab 2: 파일 분류` 이동
2. 파일 업로드 및 분류 시작

### 7.3 **Step 3: 자동화 모니터링 (New!)**
1. [Flower 대시보드](http://localhost:5555) 접속
2. `Tasks` 탭에서 자동 재분류/리포트 생성 작업 확인
3. `System` 탭에서 워커 상태 확인

### 7.4 **Step 4: CLI 사용**
```bash
# 단일 파일 분류
python -m backend.cli classify "path/to/file.txt" [user_id]
```

---

## 8. 📈 개발 히스토리

### Issue별 개발 진행도

| Issue | 완료일 | 핵심 기능 | 상태 |
|-------|--------|-----------|------|
| [#1-10] | ~11/11 | Phase 1-2 (MVP) | ✅ |
| [#10.4] | 12/16 | Celery 자동화 & 스케줄링 | ✅ |

### 주요 커밋 히스토리
- `...` - Phase 3 구현
- `current` - Phase 4 Celery Automation (Worker, Beat, Monitoring)

---

## 9. 🗺️ 로드맵

### ✅ 완료된 기능 (v5.0)
- [x] 스마트 온보딩 & PARA 분류
- [x] Celery 기반 비동기 작업 큐
- [x] 정기 자동 재분류 및 아카이빙 스케줄러
- [x] Flower 모니터링 통합
- [x] MCP 서버 구현 ✨
- [x] Obsidian 동기화 및 충돌 해결 ✨
- [x] Next.js 기반 모던 대시보드 ✨
- [x] PARA Graph View & Advanced Stats ✨
- [x] Mobile Responsive UI ✨

### 🚧 진행 중 (v6.0)
- [ ] WebSocket 실시간 업데이트
- [ ] Conflict Diff Viewer
- [ ] 다국어 지원 (i18n)

---

## 10. ❓ FAQ

### Q1. Redis가 꼭 필요한가요?
**A**: 네, Celery의 메시지 브로커로 Redis를 사용하므로 반드시 실행되어 있어야 합니다.

### Q2. 자동화 작업은 언제 실행되나요?
**A**: `backend/celery_app/config.py`에 정의된 스케줄에 따릅니다. (예: 재분류-매일 00:00)

---

## 11. 🤝 기여하기
Issues 제보 및 PR 환영합니다.

---

## 12. 📄 라이선스
MIT License

---

## 13. 👤 개발자
**Jay** ([@jjaayy2222](https://github.com/jjaayy2222))

---

<br>

<p align="center">
  <strong>FlowNote</strong> - AI가 당신의 문서를 정리해줍니다 🚀
</p>

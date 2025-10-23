# FlowNote MVP

AI 대화를 체계적으로 저장하고 검색하는 도구

## 📖 프로젝트 소개

FlowNote는 ChatGPT, Claude, Perplexity 등 AI 도구와의 대화를 저장하고, 나중에 쉽게 찾아볼 수 있게 도와주는 로컬 우선 도구입니다.

### 핵심 기능 (MVP)

- **파일 업로드**: AI 대화 파일 (.md, .txt) 업로드
- **자동 분류**: 업무/학습/기타로 자동 카테고리 분류
- **벡터 검색**: FAISS 기반 의미 검색
- **프롬프트 템플릿**: 요약, Q&A, 키워드 추출
- **Markdown 내보내기**: 결과를 파일로 저장

## 🚀 빠른 시작

### 필요 사항

- Python 3.11
- pyenv (권장)
- OpenAI API Key

### 설치

```bash

# 1. 리포지토리 클론
git clone https://github.com/jjaayy2222/flownote-mvp.git
cd flownote-mvp

# 2. Python 버전 설정 (자동)
# .python-version 파일이 있어서 자동으로 3.11.10 사용

# 3. 가상환경 생성 및 활성화
# pyenv virtualenv 3.11.10 <원하는 가상환경 명칭>
pyenv virtualenv 3.11.10 myenv
pyenv activate myenv

# 4. 패키지 설치
pip install -r requirements.txt

# 5. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 각자의 OPENAI_API_KEY 입력

# 6. 실행
streamlit run app.py

```

## 📁 프로젝트 구조

```
flownote-mvp/
├── .python-version      # Python 버전 (3.11.10)
|
├── requirements.txt     # 패키지 의존성
|
├── .env                 # 환경변수 (git 무시)
|
├── .gitignore
|
├── README.md

├── docs/
│   ├── constitution.md  # 프로젝트 헌장
│   └── specs/           # 기능 명세
│       ├── file-upload.md
│       ├── faiss-search.md
│       ├── prompt-templates.md
│       ├── markdown-export.md
│       └── mcp-classification.md
|
├── backend/             # 백엔드 로직 (예정)
|
├── data/                # (에정)
│   ├── uploads/            # 업로드된 파일
│   ├── faiss/              # FAISS 인덱스
│   └── exports/            # 내보낸 파일
|
└── temp/                # 임시 파일

```

## 🛠️ 기술 스택

- **프레임워크**: Streamlit
- **LLM**: LangChain + OpenAI API
- **벡터 DB**: FAISS (로컬)
- **패키지 관리**: pyenv + pip
- **버전**: Python 3.11.10

## 📚 문서

- [Constitution](docs/constitution.md) - 프로젝트 철학과 원칙
- [Feature Specs](docs/specs/) - 기능 명세서

## 🔗 관련 링크

- [이슈 트래커](https://github.com/jjaayy2222/flownote-mvp/issues)
- [프로젝트 보드](https://github.com/jjaayy2222/flownote-mvp/projects)

## 📅 타임라인

- **MVP (10.23-10.31)**: 핵심 기능 구현
- **v1.1 (11.5-11.16)**: Notion 연동 + 인사이트 *(예정)*
- **v1.2 (미정)**: 공유 기능

## 📄 라이선스

MIT License

## 👤 작성자

Jay - [@jjaayy2222](https://github.com/jjaayy2222)

---

**FlowNote** - AI 대화를 흘려보내지 않고 기록하고 활용하세요.
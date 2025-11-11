# Streamlit 환경변수 & API KEY 설정 가이드

> **작성일:** 2025-11-06  
> **소요 시간:** 약 1.5시간  
> **최종 결과:** 로컬 + 배포 환경 모두 API KEY 정상 인식

***

## 📋 목차

1. [문제 상황 분석](#1-문제-상황-분석)
2. [로컬 개발 환경 설정](#2-로컬-개발-환경-설정)
3. [Streamlit Secrets 설정](#3-streamlit-secrets-설정)
4. [배포 환경 설정](#4-배포-환경-설정)
5. [디버깅 팁](#5-디버깅-팁)

***

## 1. 문제 상황 분석

### 1.1 발생한 오류

```bash
❌ KeyError: 'OPENAI_API_KEY'
❌ Environment variable not found
❌ 로컬에서는 되는데 배포에서는 안 됨
```

### 1.2 원인

**로컬 (.env 파일):**
- Python-dotenv 자동 로드
- 개발 환경에서만 적용

**배포 (Streamlit Cloud):**
- .env 파일 무시됨 (보안)
- Streamlit Secrets 필수
- 또는 환경변수 설정 필요

---

## 2. 로컬 개발 환경 설정

### 2.1 .env 파일 생성

```bash
    # 프로젝트 루트에서
    cat > .env << EOF
    OPENAI_API_KEY=sk-your-key-here
    EMBEDDING_MODEL=text-embedding-3-small
    DEBUG=False
    EOF

    # 또는 수동으로 .env 파일 생성 후 추가
    OPENAI_API_KEY=sk-...
    EMBEDDING_MODEL=text-embedding-3-small
    DEBUG=False
```

### 2.2 Python 코드에서 로드

```python
    import os
    from dotenv import load_dotenv

    # .env 파일 로드
    load_dotenv()

    # 환경변수 읽기
    api_key = os.getenv("OPENAI_API_KEY")
    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in .env file")

    print(f"✅ API Key loaded: {api_key[:10]}...")
```

### 2.3 .gitignore에 추가

```bash
    # .gitignore
    .env
    .env.local
    .env.*.local
```

***

## 3. Streamlit Secrets 설정

### 3.1 로컬 Secrets 파일

```bash
    # 경로: ~/.streamlit/secrets.toml
    # 또는 [프로젝트]/.streamlit/secrets.toml

    # 파일 생성
    mkdir -p .streamlit
    cat > .streamlit/secrets.toml << EOF
    OPENAI_API_KEY = "sk-your-key-here"
    EMBEDDING_MODEL = "text-embedding-3-small"
    DEBUG = false
    EOF
```

### 3.2 Streamlit 코드에서 접근

```python
    import streamlit as st

    # Secrets 읽기
    api_key = st.secrets["OPENAI_API_KEY"]
    embedding_model = st.secrets.get("EMBEDDING_MODEL", "text-embedding-3-small")

    if not api_key:
        st.error("❌ OPENAI_API_KEY not configured!")
        st.stop()

    st.success(f"✅ Secrets loaded successfully!")
```

### 3.3 secrets.toml 포맷

```toml
    # TOML 형식
    [section]
    key = "value"

    # 또는 직접
    OPENAI_API_KEY = "sk-..."
    DATABASE_URL = "postgresql://..."
    DEBUG = true

    # 리스트
    ALLOWED_MODELS = ["gpt-4", "gpt-3.5-turbo"]

    # 숫자
    MAX_RETRIES = 3
    TIMEOUT = 30
```

***

## 4. 배포 환경 설정

### 4.1 Streamlit Cloud Secrets 설정

**단계별 가이드:**

```bash
    1️⃣ Streamlit Cloud 접속
        https://share.streamlit.io

    2️⃣ 앱 클릭 또는 "New app" 클릭

    3️⃣ 앱 관리 페이지 열기
        → "Settings" 또는 "⚙️" 아이콘

    4️⃣ "Secrets" 탭 클릭

    5️⃣ TOML 형식으로 입력:
        OPENAI_API_KEY = "sk-..."
        EMBEDDING_MODEL = "text-embedding-3-small"

    6️⃣ "Save" 클릭 (자동 배포 시작)
```

### 4.2 TOML 포맷 주의사항

```toml
    # ✅ 올바른 형식
    OPENAI_API_KEY = "sk-..."
    TIMEOUT = 30
    DEBUG = true

    # ❌ 잘못된 형식
    OPENAI_API_KEY: sk-...        # 콜론 사용 X
    OPENAI_API_KEY = 'sk-...'     # 작은따옴표 X (큰따옴표 필수)
    TIMEOUT = "30"                # 숫자는 따옴표 X
```

***

## 5. 디버깅 팁

### 5.1 환경변수 확인 코드

```python
    import streamlit as st
    import os

    st.write("### 🔍 Environment Variables Debug")

    # 로컬 .env
    try:
        api_key_env = os.getenv("OPENAI_API_KEY")
        st.write(f"✅ os.getenv: {api_key_env[:10] if api_key_env else '❌ Not found'}...")
    except Exception as e:
        st.write(f"❌ os.getenv error: {e}")

    # Streamlit Secrets
    try:
        api_key_secret = st.secrets.get("OPENAI_API_KEY")
        st.write(f"✅ st.secrets: {api_key_secret[:10] if api_key_secret else '❌ Not found'}...")
    except Exception as e:
        st.write(f"❌ st.secrets error: {e}")

    # 우선순위
    final_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    st.write(f"✅ Final key (if any): {final_key[:10] if final_key else '❌ None'}...")
```

### 5.2 문제 해결 체크리스트

```
  로컬 개발:
    □ .env 파일 존재 (프로젝트 루트)
    □ python-dotenv 설치 (pip install python-dotenv)
    □ load_dotenv() 호출됨
    □ .gitignore에 .env 추가됨

  배포:
    □ Streamlit Cloud에 Secrets 설정됨
    □ TOML 포맷 올바름 (큰따옴표, 콜론 X)
    □ 앱 재배포됨 (자동 또는 수동)
    □ Logs에서 에러 확인 (없으면 정상)

  코드:
    □ st.secrets 또는 os.getenv() 사용
    □ 환경변수 이름 정확함
    □ 에러 처리 있음 (if not key: ...)
```

***

## 📚 참고 자료

- [Streamlit Secrets 공식 문서](https://docs.streamlit.io/streamlit-cloud/get-started/deploy-an-app/secrets-management)
- [Python-dotenv 문서](https://github.com/theskumar/python-dotenv)

***
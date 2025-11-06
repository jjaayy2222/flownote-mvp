# Streamlit 배포 문제 해결 가이드

> **작성일:** 2025-11-06  
> **소요 시간:** 약 2시간  
> **최종 결과:** Streamlit Cloud 배포 성공

---

## 📋 목차

1. [문제 상황 분석](#1-문제-상황-분석)
2. [배포 플랫폼 체크리스트](#2-배포-플랫폼-체크리스트)
3. [일반적인 배포 문제들](#3-일반적인-배포-문제들)
4. [최종 해결 방법](#4-최종-해결-방법)
5. [배포 후 확인사항](#5-배포-후-확인사항)

---

## 1. 문제 상황 분석

### 1.1 발생한 증상

```
❌ 배포 링크 안 열림
❌ 배포했는데 접속 불가
❌ 에러 페이지 또는 무한 로딩
```

### 1.2 확인해야 할 것들

**배포 플랫폼 확인:**

- ☁️ Streamlit Cloud
- 📦 Vercel
- 🔧 Heroku
- 📄 GitHub Pages
- 기타

**배포 URL 형식 예시:**

```
✅ https://[username]-flownote-[random].streamlit.app
✅ https://[username].github.io/flownote-mvp
✅ https://[project-name].vercel.app
```

---

## 2. 배포 플랫폼 체크리스트

### 2.1 Streamlit Cloud 배포

```
# ✅ 필수 파일
- streamlit_app.py (또는 app.py)
- requirements.txt
- .streamlit/config.toml (권장)

# ⚠️ 주의: 폴더 구조
streamlit_app.py 위치:
  ✅ 프로젝트 루트 (권장)
  ⚠️ 하위 폴더 (경로 지정 필요)

# 배포 설정 확인
Streamlit Cloud Dashboard
→ "Deploy" 또는 "Edit App"
→ 올바른 파일 경로인지 확인
```

### 2.2 requirements.txt 확인

```
# 필수 확인!
ls -la | grep requirements

# 있으면 (Good!)
✅ requirements.txt

# 없으면 (Bad!)
❌ 배포 서버가 뭘 설치해야 할지 몰라서 에러!

# 빠진 라이브러리 있으면 추가
streamlit>=1.28.0
pandas
numpy
# ... 기타 필요한 패키지
```

---

## 3. 일반적인 배포 문제들

### 3.1 문제: streamlit_app.py 찾을 수 없음

```bash
❌ Error: No such file or directory: 'streamlit_app.py'
```

**원인:**
- 파일이 루트에 없고 하위 폴더에 있음
- 파일명이 다름 (app.py vs streamlit_app.py)

**해결:**

**옵션 1: 파일명 변경**
```bash
mv streamlit/app.py streamlit_app.py
```

**옵션 2: 경로 지정 (권장)**
```bash
# .streamlit/config.toml 추가
[client]
toolbarMode = "minimal"

[logger]
level = "info"

# 또는 streamlit 설정에서
# "main file path" 지정
```

### 3.2 문제: requirements.txt 누락

```bash
❌ ModuleNotFoundError: No module named 'streamlit'
```

**해결:**

```bash
# requirements.txt 생성
pip freeze > requirements.txt

# 배포 후 자동으로 설치됨
```

### 3.3 문제: 환경변수 인식 안 됨

```bash
❌ KeyError: OpenAI API key not found
```

**해결:**

```
# Streamlit Secrets 설정 (나중 섹션 참고)
# 또는 .env.example 작성
OPENAI_API_KEY=your_key_here
```

---

## 4. 최종 해결 방법

### 4.1 배포 전 체크리스트

```bash
□ requirements.txt 존재
□ 메인 파일 (streamlit_app.py 또는 app.py) 존재
□ .streamlit/config.toml 설정 (권장)
□ 모든 import 모듈이 requirements.txt에 포함
□ 환경변수 설정 (.streamlit/secrets.toml)
```

### 4.2 배포 단계

```bash
# 1️⃣ 로컬에서 테스트
streamlit run streamlit_app.py

# 2️⃣ 깃 푸시
git add .
git commit -m "feat: Streamlit deployment"
git push origin main

# 3️⃣ Streamlit Cloud에서 배포
# - Streamlit Cloud 접속
# - "New app" → GitHub 연결
# - 리포지토리 선택 후 배포
```

---

## 5. 배포 후 확인사항

### 5.1 배포 링크 테스트

```
✅ URL이 열리는가?
✅ 모든 기능이 작동하는가?
✅ API 호출이 정상인가?
✅ 오류 메시지가 없는가?
```

### 5.2 배포 로그 확인

```bash
# Streamlit Cloud Dashboard
→ 앱 클릭
→ "Manage app"
→ "Logs" 탭
→ 에러 메시지 확인
```

### 5.3 자주 발생하는 배포 후 문제

```bash
❌ 자동 업데이트 안 됨
→ 수동 재배포 또는 GitHub 웹훅 재설정

❌ API 호출 실패
→ Streamlit Secrets 확인 (다음 섹션)

❌ 라이브러리 버전 충돌
→ requirements.txt에 정확한 버전 명시
```

---

## 📚 참고 자료

- [Streamlit Cloud 공식 문서](https://docs.streamlit.io/streamlit-cloud)
- [Streamlit 배포 튜토리얼](https://docs.streamlit.io/library/get-started/create-an-app)

---

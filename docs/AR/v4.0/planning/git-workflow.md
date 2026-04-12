# Git Workflow & Branch Strategy

## 📌 브랜치 전략

### 영구 브랜치
- `main`: 안정 버전 (항상 배포 가능)
- `setup/frontend-react`: React 마이그레이션 (미래 v5+)

### 임시 브랜치
- `refactor/v*-*`: 리팩토링 작업
- `feat/*`: 새 기능 개발
- `fix/*`: 버그 수정
- `release/*`: 릴리스 준비

## 🔄 작업 플로우

### 1. 새 작업 시작
```bash
git checkout main
git pull origin main
git checkout -b <type>/<description>
```

### 2. 작업 진행
```bash
# 작은 단위로 자주 커밋
git add .
git commit -m "type: description"
```

### 3. 완료 후
```bash
# GitHub에 푸시
git push origin <branch-name>

# PR 생성 (GitHub 웹)
# 리뷰 → 머지 → 로컬/원격 브랜치 삭제
```

## 📋 커밋 메시지 규칙

- `feat`: 새 기능
- `fix`: 버그 수정
- `refactor`: 리팩토링
- `docs`: 문서 수정
- `test`: 테스트 추가
- `chore`: 기타 작업

예시:
```bash
feat[#11]: Add batch classification feature
fix: Resolve FAISS index loading error
refactor: Consolidate duplicate models
docs: Update API documentation
```

## 🗑️ 브랜치 삭제 규칙

### 삭제해야 하는 경우
- main에 머지 완료
- 작업 포기/중단

### 삭제 방법
```bash
# 로컬 삭제
git branch -d <branch-name>

# 원격 삭제
git push origin --delete <branch-name>
```

## 📌 태그 전략

- 버전 릴리스 시 태그 생성
- 형식: `v<major>.<minor>.<patch>`
- 예시: `v3.5.0`, `v4.0.0`

```bash
git tag v4.0.0 -m "Backend refactoring complete"
git push origin v4.0.0
```

## 🎯 현재 상태 (2025-11-13)

### 활성 브랜치
- `main` (v3.5.0)
- `refactor/v4-backend-cleanup` (진행 중)
- `setup/frontend-react` (보류)

### 다음 작업
- v4.0 리팩토링 진행
- 완료 후 PR + 태그

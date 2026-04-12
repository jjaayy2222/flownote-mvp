# Git 브랜치 정리 및 운영 계획

> **작성일**: 2025-11-13  
> **현재 버전**: v3.5 (제출 완료)  
> **다음 버전**: v4.0 (Backend Refactoring)

---

## 📊 현재 브랜치 현황

### 전체 브랜치 목록
```bash
  develop                                # ❓ 용도 불명
  feat/dashboard-conflict-resolver       # 🔴 v3 완료 (정리 대상)
* feat/dashboard-para-api-integration    # 🔴 v3 완료 (현재 위치)
  feat/dashboard-para-classification     # 🔴 v3 완료 (정리 대상)
  feat/vision-api                        # 🔴 v3 완료 (정리 대상)
  main                                   # ✅ 안정 버전
  setup/frontend-react                   # 🟡 미래 계획
```

### 브랜치별 상태 분석

| 브랜치 | 용도 | 상태 | 조치 |
|--------|------|------|------|
| `main` | 배포/안정 버전 | ✅ 유지 | PR 머지 대상 |
| `develop` | 개발 통합? | ❓ 미사용 | 🗑️ 삭제 권장 |
| `feat/dashboard-*` (3개) | v3 기능 개발 | 🔴 완료 | 🗑️ 정리 후 삭제 |
| `feat/vision-api` | v3 Vision API | 🔴 완료 | 🗑️ 정리 후 삭제 |
| `setup/frontend-react` | 미래 계획 | 🟡 보류 | 📌 보존 (나중에 사용) |

---

## 🎯 정리 목표

### 1. v3 완료 기념 PR 생성
- 모든 v3 작업을 문서화
- GitHub에 공식 기록 남기기

### 2. 불필요한 브랜치 삭제
- v3 완료된 feature 브랜치 정리
- main에 이미 머지된 브랜치 삭제

### 3. v4 작업을 위한 브랜치 생성
- 리팩토링 전용 브랜치
- 명확한 네이밍 규칙

---

## 📝 Step-by-Step 실행 계획

### Phase 1: 현재 상태 백업 및 확인 (5분)

#### Step 1-1: 현재 위치 확인
```bash
# 현재 어느 브랜치에 있는지 확인
git branch

# 현재 브랜치에 변경사항이 있는지 확인
git status

# 결과 예시:
# On branch feat/dashboard-para-api-integration
# nothing to commit, working tree clean
```

**💡 설명**:
- `*` 표시가 현재 브랜치
- "nothing to commit"이면 안전하게 진행 가능

#### Step 1-2: main 브랜치로 이동
```bash
# main 브랜치로 전환
git checkout main

# main이 최신 상태인지 확인
git pull origin main

# 결과:
# Already up to date. (이미 최신이면 이 메시지)
```

**💡 설명**:
- main은 항상 최신 상태여야 함
- 혹시 모를 충돌 방지

#### Step 1-3: 모든 브랜치 상태 저장
```bash
# 모든 브랜치 목록을 파일로 저장
git branch -a > branches_backup.txt

# 각 브랜치의 마지막 커밋 저장
git log --all --oneline --graph --decorate > git_history_backup.txt

# 파일 확인
cat branches_backup.txt
```

**💡 설명**:
- 혹시 실수로 삭제해도 복구 가능
- 백업은 항상 먼저!

---

### Phase 2: v3 완료 PR 생성 (15분)

#### Step 2-1: v3 통합 브랜치 생성
```bash
# v3 작업을 정리할 임시 브랜치 생성
git checkout -b release/v3.5-final

# main의 최신 내용을 가져오기
git merge main

# 결과:
# Already up to date. (이미 최신이면)
```

**💡 설명**:
- `release/v3.5-final`은 v3 전체를 대표하는 브랜치
- PR 생성용 임시 브랜치

#### Step 2-2: v3 작업 요약 문서 생성
```bash
# docs/releases/ 디렉토리 생성
mkdir -p docs/releases

# v3.5 릴리스 노트 작성
cat > docs/releases/v3.5-release-notes.md << 'EOF'
# FlowNote v3.5 Release Notes

## 📅 릴리스 정보
- **버전**: v3.5
- **릴리스 날짜**: 2025-11-12
- **상태**: 프로젝트 제출 완료 ✅

## ✨ 주요 기능

### 1. 스마트 온보딩 (#8)
- GPT-4o 기반 영역 추천 시스템
- 사용자 맥락 자동 저장
- 10개 추천 → 5개 선택 플로우

### 2. AI 기반 PARA 분류 (#9)
- LangChain 통합 분류 엔진
- 사용자 직업/관심 영역 반영
- 신뢰도 점수 + 키워드 태그

### 3. 실시간 대시보드 (#10)
- 분류 통계 시각화
- 파일 트리 구조 표시
- 메타데이터 관리

### 4. Vision API 통합 (#4)
- 이미지 기반 코드 생성
- GPT-4.1 모델 사용

## 🔧 기술 스택
- Backend: FastAPI + LangChain
- Frontend: Streamlit
- AI: OpenAI GPT-4o, GPT-4o-mini, GPT-4.1
- DB: SQLite
- Search: FAISS

## 📊 개발 이슈
- Issue #1-10 완료
- 총 커밋: 약 50개
- 총 작업 기간: 2024.10.23 - 2025.11.12

## 🎯 다음 버전 (v4.0)
- Backend 리팩토링
- 코드 구조 개선
- 테스트 커버리지 향상
EOF
```
```bash
# 파일 확인
cat docs/releases/v3.5-release-notes.md
```

**💡 설명**:
- v3 작업을 한 눈에 볼 수 있는 문서
- PR 설명에 사용할 내용

#### Step 2-3: GitHub에 푸시
```bash
# 변경사항 커밋
git add docs/releases/v3.5-release-notes.md
git commit -m "📝 Add v3.5 release notes

- Document all v3 features
- Prepare for v3 → v4 transition
- List completed issues #1-#10
"

# GitHub에 푸시
git push origin release/v3.5-final
```

**💡 설명**:
- GitHub에 브랜치가 올라가면 PR 생성 가능

#### Step 2-4: GitHub에서 PR 생성

**웹 브라우저에서**:

1. **GitHub 저장소로 이동**
   ```
   https://github.com/jjaayy2222/flownote-mvp
   ```

2. **"Compare & pull request" 버튼 클릭**
   - 노란색 배너에 자동으로 표시됨
   - 또는 "Pull requests" 탭 → "New pull request"

3. **PR 정보 입력**:

   ```markdown
   Title: 🎉 Release v3.5: Complete Project Submission
   
   Base: main ← Compare: release/v3.5-final
   
   Description:
   
   ## 📋 Summary
   
   FlowNote v3.5 프로젝트 제출 완료를 기념하는 PR입니다.
   
   ## ✨ What's New
   
   ### 주요 기능
   - ✅ #8: 스마트 온보딩 (GPT-4o 영역 추천)
   - ✅ #9: AI 기반 PARA 자동 분류
   - ✅ #10: 실시간 대시보드
   - ✅ #4: Vision API 통합
   
   ### 완료된 이슈
   - Issue #1 ~ #10 (총 10개)
   
   ### 브랜치 정리
   이 PR 머지 후 다음 브랜치들을 삭제할 예정:
   - `feat/dashboard-conflict-resolver`
   - `feat/dashboard-para-api-integration`
   - `feat/dashboard-para-classification`
   - `feat/vision-api`
   
   ## 📊 Stats
   
   - 총 커밋: ~50개
   - 작업 기간: 2024.10.23 - 2025.11.12
   - 코드 라인: +5000 (추정)
   
   ## 🎯 Next Steps
   
   - v4.0: Backend 리팩토링
   - 브랜치 정리
   - 새로운 refactor 브랜치 생성
   
   ## 📝 Release Notes
   
   상세 내용: [v3.5-release-notes.md](docs/releases/v3.5-release-notes.md)
   ```

4. **"Create pull request" 클릭**

5. **자가 리뷰 및 머지**
   - "Merge pull request" 버튼 클릭
   - "Confirm merge" 클릭
   - 완료! 🎉

**💡 설명**:
- PR은 작업 기록을 남기는 공식 문서
- 나중에 "무엇을 했는지" 확인 가능
- 포트폴리오로도 활용 가능

---

### Phase 3: 불필요한 브랜치 정리 (10분)

#### Step 3-1: main 브랜치로 복귀
```bash
# main으로 이동
git checkout main

# 최신 상태로 업데이트 (PR 머지 반영)
git pull origin main

# 태그 추가 (v3.5 공식 기록)
git tag v3.5.0 -m "Release v3.5: Project submission complete"
git push origin v3.5.0
```

**💡 설명**:
- 태그는 특정 시점을 영구 보존
- 나중에 "v3.5 코드"를 정확히 찾을 수 있음

#### Step 3-2: 로컬 브랜치 삭제
```bash
# v3 완료된 feature 브랜치 삭제
git branch -d feat/dashboard-conflict-resolver
git branch -d feat/dashboard-para-api-integration
git branch -d feat/dashboard-para-classification
git branch -d feat/vision-api

# release 브랜치도 삭제 (이미 main에 머지됨)
git branch -d release/v3.5-final

# develop 브랜치 삭제 (사용 안 함)
git branch -d develop

# 결과 확인
git branch
```

**💡 예상 결과**:
```bash
* main
  setup/frontend-react
```

**💡 설명**:
- `-d` 옵션: 안전 삭제 (머지 확인)
- 에러 나면 `-D` 사용 (강제 삭제, 주의!)

#### Step 3-3: 원격 브랜치 삭제
```bash
# GitHub에서도 삭제
git push origin --delete feat/dashboard-conflict-resolver
git push origin --delete feat/dashboard-para-api-integration
git push origin --delete feat/dashboard-para-classification
git push origin --delete feat/vision-api
git push origin --delete release/v3.5-final
git push origin --delete develop

# 결과 확인
git branch -a
```

**💡 설명**:
- 로컬 + 원격 둘 다 삭제해야 완전히 정리됨
- GitHub 저장소도 깔끔해짐

---

### Phase 4: v4 브랜치 생성 (5분)

#### Step 4-1: 리팩토링 브랜치 생성
```bash
# v4 리팩토링 브랜치
git checkout -b refactor/v4-backend-cleanup

# 확인
git branch

# 결과:
# * refactor/v4-backend-cleanup
#   main
#   setup/frontend-react
```

**💡 설명**:
- 이 브랜치에서 모든 리팩토링 작업 진행
- Phase 0-4 모두 여기서 커밋

#### Step 4-2: 브랜치 전략 문서화
```bash
# 브랜치 운영 규칙 문서 생성
cat > docs/P/git-workflow.md << 'EOF'
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

git checkout main
git pull origin main
git checkout -b <type>/<description>


### 2. 작업 진행

# 작은 단위로 자주 커밋
git add .
git commit -m "type: description"


### 3. 완료 후

# GitHub에 푸시
git push origin <branch-name>

# PR 생성 (GitHub 웹)
# 리뷰 → 머지 → 로컬/원격 브랜치 삭제


## 📋 커밋 메시지 규칙

- `feat`: 새 기능
- `fix`: 버그 수정
- `refactor`: 리팩토링
- `docs`: 문서 수정
- `test`: 테스트 추가
- `chore`: 기타 작업

예시:

feat[#11]: Add batch classification feature
fix: Resolve FAISS index loading error
refactor: Consolidate duplicate models
docs: Update API documentation


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


## 📌 태그 전략

- 버전 릴리스 시 태그 생성
- 형식: `v<major>.<minor>.<patch>`
- 예시: `v3.5.0`, `v4.0.0`


git tag v4.0.0 -m "Backend refactoring complete"
git push origin v4.0.0


## 🎯 현재 상태 (2025-11-13)

### 활성 브랜치
- `main` (v3.5.0)
- `refactor/v4-backend-cleanup` (진행 중)
- `setup/frontend-react` (보류)

### 다음 작업
- v4.0 리팩토링 진행
- 완료 후 PR + 태그


EOF
```
```bash
# 파일 확인
cat docs/P/git-workflow.md

# 커밋
git add docs/P/git-workflow.md
git commit -m "📝 Add Git workflow documentation

- Branch strategy
- Commit message rules
- Tag guidelines
"

# 푸시
git push origin refactor/v4-backend-cleanup
```

**💡 설명**:
- 앞으로의 Git 사용 규칙
- 팀 협업 시에도 활용 가능

---

## 📊 정리 결과

### Before (정리 전)
```bash
  develop                                # ❓
  feat/dashboard-conflict-resolver       # 🔴
  feat/dashboard-para-api-integration    # 🔴
  feat/dashboard-para-classification     # 🔴
  feat/vision-api                        # 🔴
  main                                   # ✅
  setup/frontend-react                   # 🟡
```

### After (정리 후)
```bash
  main                                   # ✅ v3.5.0 (안정)
  refactor/v4-backend-cleanup            # 🚀 v4.0 작업 중
  setup/frontend-react                   # 🟡 미래 (v5+)
```

---

## ✅ 체크리스트

### Phase 1: 백업 및 확인
- [ ] `git branch` 실행
- [ ] `git status` 확인
- [ ] `git checkout main`
- [ ] 백업 파일 생성

### Phase 2: v3 PR 생성
- [ ] `release/v3.5-final` 브랜치 생성
- [ ] 릴리스 노트 작성
- [ ] GitHub에 푸시
- [ ] PR 생성 및 머지

### Phase 3: 브랜치 정리
- [ ] main으로 복귀
- [ ] v3.5.0 태그 생성
- [ ] 로컬 브랜치 삭제 (6개)
- [ ] 원격 브랜치 삭제 (6개)
- [ ] `git branch -a` 확인

### Phase 4: v4 준비
- [ ] `refactor/v4-backend-cleanup` 생성
- [ ] `git-workflow.md` 작성
- [ ] 첫 커밋 + 푸시

---

## 🚨 주의사항

### 1. 브랜치 삭제 전 확인
```bash
# 삭제 전 반드시 확인!
git log <branch-name> --oneline

# main에 머지되었는지 확인
git branch --merged main
```

### 2. 실수로 삭제한 경우
```bash
# 최근 삭제된 브랜치 복구
git reflog
git checkout -b <branch-name> <commit-hash>
```

### 3. 원격 브랜치 삭제 후
```bash
# 로컬에 남은 원격 추적 브랜치 정리
git fetch --prune
```

---

## 🎯 다음 단계

1. **이 문서대로 실행** (약 35분 소요)
2. **v4 리팩토링 시작** (`refactoring_plan_v2.md` 참고)
3. **Phase 0부터 진행** (베이스라인 설정)
4. **v4 완료 후 다시 PR + 태그**

---

## 📚 참고 자료

- [Git 공식 문서](https://git-scm.com/doc)
- [GitHub Flow](https://guides.github.com/introduction/flow/)
- [Semantic Versioning](https://semver.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)


**💡 설명**:
- 모든 Git 작업 규칙을 문서화
- 나중에 헷갈릴 때 참고

---

## 🎯 최종 요약

### 실행 순서
1. **백업** (5분) → 안전장치
2. **v3 PR** (15분) → 공식 기록
3. **브랜치 정리** (10분) → 깔끔하게
4. **v4 준비** (5분) → 새 출발

### 예상 결과
```bash
# 최종 브랜치 구조
main (v3.5.0)
└── refactor/v4-backend-cleanup (작업 중)
└── setup/frontend-react (보류)

# GitHub PR
- v3.5 릴리스 PR (머지 완료)

# 태그
- v3.5.0 (현재)
- v4.0.0 (리팩토링 완료 후)
```

### 다음 작업
→ `refactoring_plan_v2.md`의 Phase 0부터 시작! 🚀

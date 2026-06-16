# v10 Roadmap Ideas: Production-Ready & User-Centric (기획 중)

> 상위 이슈: TBD | 마일스톤: v10.0 | 기준 브랜치: develop (v9.0)  
> 생성일: 2026-06-16 | 상태: 🌱 초기 아이디어 단계

---

## 🎯 v10 비전

v9.0에서 구축한 **적응형 AI 코어(Adaptive Intelligence Core)** 위에,  
v10에서 **프로덕션 레디(Production-Ready)** 와 **사용자 중심 경험(User-Centric UX)** 을 완성하기.

```
v9.0: 파인튜닝 → 개인화 → 사용자 적응 (인텔리전스)
v10:  보안 강화 → 멀티유저 → 배포/확장 (프로덕션)
```

> 💡 **v10 선택 이유**: v9.0 완료로 AI 코어가 완성된 시점에서, 다음 단계는 이 AI를  
> 실제 사용자들에게 안전하게 제공할 수 있는 프로덕션 수준의 인프라·보안·경험을 갖추는 것.  
> TODO.md의 P1(인증)·P2(자동화) 기술 부채도 이 단계에서 자연스럽게 해소될 수 있음.

---

## 📦 Phase 계획 총괄 (아이디어 단계)

| Phase | 코드명 (가칭) | 핵심 가치 | 연결된 TODO |
|-------|-------------|-----------|------------|
| Phase 1 | `production-auth` | 실제 인증 시스템 도입 | P1 (Authentication) |
| Phase 2 | `multi-user-scale` | 멀티유저 확장 및 권한 관리 | P2 (Automation DB) |
| Phase 3 | `ux-globalization` | 다국어 확장 및 UX 고도화 | README 로드맵 항목 |
| Phase 4 | `observability` | 운영 가시성 및 배포 자동화 | P4 (Dashboard) |

---

## 📋 Phase 1: 실제 인증 시스템 도입 (Production Auth)

> 연결 이슈: TODO.md `[P1]` 항목  
> 기술 부채 해소: `backend/api/deps.py` Mock 인증 → 실제 인증

### 배경
- 현재 `get_current_user`, `get_current_user_ws` 는 Mock 사용 중.
- 멀티유저 환경 및 프로덕션 배포를 위해 실제 인증 레이어가 필수.
- v9.0의 개인화 RAG가 실제로 동작하려면 진짜 `user_id` 가 필요함.

### 아이디어 (세부 Tasks - 미확정)
- [ ] JWT 기반 실제 토큰 인증 로직 구현 (`backend/api/deps.py` 내 `verify_token` 함수 신설 예정 — 현재 TODO 주석으로만 존재)
- [ ] `backend/core/config.py::Settings` 를 통한 글로벌 의존성 라우팅 정비
- [ ] Sync DB 충돌 레코드 영구 저장 로직 (`sync_service.py::_handle_conflict`)
- [ ] Conflict Resolution 파일 시스템(JSONL) 안전 기록 완성 (`backend/services/conflict_resolution_service.py`)

### 기대 효과
- Mock 제거로 코드베이스 신뢰성 향상
- v9.0 개인화 RAG가 실제 사용자 컨텍스트에서 동작 가능
- 프로덕션 배포 준비의 핵심 선행 조건 충족

---

## 📋 Phase 2: 멀티유저 확장 및 자동화 DB 연동 (Multi-User Scale)

> 연결 이슈: TODO.md `[P2]` 항목  
> 기술 부채 해소: `automation_manager.py`, `automation.py`, `scheduler_service.py`

### 배경
- 자동화 규칙(CRUD)이 여전히 파일/Mock 기반.
- Celery 태스크 지연 실행(`task.delay()`) 미활성화 상태.
- 멀티유저 환경에서는 사용자별 자동화 규칙 분리가 필수.

### 아이디어 (세부 Tasks - 미확정)
- [ ] Automation Rules DB 연동 전환 (파일 기반 → DB)
- [ ] Celery `trigger_automation_task` 실제 지연 실행 활성화
- [ ] Golden Dataset 조인: `session_id`, `message_id` 활용 컨텍스트 보강
- [ ] 사용자별 자동화 규칙 격리 및 권한 체계 설계

### 기대 효과
- 실제 자동화 파이프라인이 동작하는 프로덕션 수준 달성
- v8.0 Golden Dataset 품질 지표가 실제 챗 컨텍스트와 연결됨

---

## 📋 Phase 3: 다국어 확장 및 UX 고도화 (UX & Globalization)

> 연결 이슈: TODO.md `[P3]` 항목 + README 로드맵 "진행 예정" 항목  
> 기술 부채 해소: `backend/mcp/obsidian_server.py` Sync 비교 엔진, `backend/mcp/server.py` & `backend/celery_app/tasks/graph.py` Persistent Embeddings, `backend/api/endpoints/sync.py` Sync Status API

### 배경
- v6.0에서 한/영 다국어를 구축했으나, 일본어·중국어 수요가 있음.
- Obsidian Sync 실제 로직 및 Persistent Embeddings 미완성.
- 파일 버전 히스토리 기능 미구현.

### 아이디어 (세부 Tasks - 미확정)
- [ ] 추가 언어 지원: 일본어(`ja`), 중국어 간체(`zh-CN`) 번역 파일 추가
- [ ] AI 기반 자동 번역 파이프라인 (기존 i18n 키 자동 생성)
- [ ] 파일 버전 히스토리: 변경 이력 추적 및 롤백 기능
- [ ] Obsidian Sync 핵심 비교 엔진 구현 (해시 대조 기반)
- [ ] Persistent Embeddings: FAISSRetriever 활용 DB/Cache 기반 영구 로딩
- [ ] Sync Status API 실제 매니저/DB 연결 (`[P3]` 해소)

### 기대 효과
- 사용자 경험의 글로벌 확장 기반 마련
- Obsidian 연동 완결로 로컬-클라우드 동기화 신뢰성 확보

---

## 📋 Phase 4: 운영 가시성 및 배포 자동화 (Observability & DevOps)

> 연결 이슈: TODO.md `[P4]` 항목  
> 기술 부채 해소: Dashboard Stats, Metadata API, Reporting Task

### 배경
- Dashboard 통계가 임시 수치(Mock) 기반.
- Reporting Task가 DB 쿼리가 아닌 메모리 기반으로 성능 제한.
- CI/CD 파이프라인의 프로덕션 배포 자동화 미비.

### 아이디어 (세부 Tasks - 미확정)
- [ ] Dashboard 실제 로그·지표 집계 연동 (`get_dashboard_summary`, `get_watchdog_events`)
- [ ] Metadata API 실제 조회·업데이트 기능 연동
- [ ] Reporting Task DB 쿼리 기반 성능 최적화
- [ ] Prometheus + Grafana 기반 메트릭 모니터링 도입
- [ ] GitHub Actions 기반 자동 배포(CD) 파이프라인 강화

### 기대 효과
- 운영 중 장애를 즉시 감지하고 대응할 수 있는 가시성 확보
- TODO.md `[P4]` 기술 부채 전면 해소

---

## 🌿 브랜치 전략 (가칭)

```
main
 └── develop
      └── feature/v10-production-ready  ← 중간 상위 브랜치 (예정)
           ├── feature/issue-XXXX-production-auth     (Phase 1)
           ├── feature/issue-XXXX-multi-user-scale    (Phase 2)
           ├── feature/issue-XXXX-ux-globalization    (Phase 3)
           └── feature/issue-XXXX-observability       (Phase 4)
```

> ⚠️ 이슈 번호(XXXX)는 GitHub 이슈 생성 후 확정 예정.

---

## 🔗 연결 문서

- **기술 부채 출처**: [`docs/A/TODO.md`](../A/TODO.md)
- **v9.0 완료 현황**: [`docs/AR/v9.0/v9.0_roadmap.md`](../AR/v9.0/v9.0_roadmap.md)
- **프로젝트 헌법**: [`docs/A/specifications/constitution.md`](../A/specifications/constitution.md)

---

## 🗓️ 마일스톤 설정 (초안)

### Milestone: v10.0
- **Title**: v10.0 - Production-Ready & User-Centric
- **Description**: 실제 인증 시스템, 멀티유저 확장, 다국어 UX 고도화, 운영 가시성 완성을 통한 프로덕션 레디 달성
- **Due Date**: TBD

---

## 💭 열린 질문 (Open Questions)

> 기획 확정 전 논의가 필요한 항목들입니다.

1. **v10 vs v9.1**: 마이너 업데이트(v9.1)로 일부 Phase만 먼저 진행할지,  
   메이저 업데이트(v10)로 전체 비전을 한 번에 잡을지?
2. **인증 방식**: JWT 자체 구현 vs Auth0/Firebase Auth 외부 서비스 활용?
3. **다국어 번역**: 수동 번역 vs AI 자동 번역 파이프라인 구축?
4. **배포 대상**: Render(현재) 유지 vs AWS/GCP 전환?

---

*생성일: 2026-06-16 | 기준 브랜치: develop (v9.0) | 상태: 🌱 초기 아이디어 — 확정 전 자유롭게 수정 가능*

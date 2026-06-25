# FlowNote MVP - TODO & FIXME 추적 문서

본 문서는 코드베이스 전반에 산재되어 있는 `TODO` 및 `FIXME` 주석들을 중앙에서 추적하고 관리하기 위해 생성되었습니다.

## 🔴 [P1] Phase 2: Authentication & Core DB 연동
보안 및 핵심 데이터 무결성과 직결되므로 최우선으로 해결해야 할 부채입니다.

- [ ] **Authentication (`backend/api/deps.py`)**
  - `get_current_user` 및 `get_current_user_ws` 함수: 현재 Mock 사용 중인 부분을 `verify_token(token)` 기반 실제 인증 로직으로 대체.
  - 전역 의존성을 `backend.config.AppConfig`를 통해 라우팅하도록 개선.
- [ ] **Sync DB (`backend/services/sync_service.py`)**
  - `_handle_conflict` 메서드: 충돌 발생 시 DB에 충돌 레코드를 영구 저장하는 로직.
- [ ] **Conflict Resolution (`backend/services/conflict_resolution_service.py`)**
  - 파일 시스템(JSONL) 안전 기록 및 `PathConfig` 활용 보완.

## 🟠 [P2] Phase 3: Automation & Scheduler 구현
자동화 작업의 실질적인 동작과 데이터 신뢰성을 보장하는 항목입니다.

- [ ] **Automation Rules DB 연동 (`backend/services/automation_manager.py`)**
  - `get_automation_rules`, `create_automation_rule` 등 규칙 CRUD 전체 메서드: 파일/Mock 기반에서 DB 연동으로 전환.
- [ ] **Celery 연동 (`backend/api/endpoints/automation.py`)**
  - `trigger_automation_task` 엔드포인트: 실제 Celery 태스크 지연 실행(`task.delay()`) 트리거 활성화.
- [ ] **Golden Dataset 조인 (`backend/services/scheduler_service.py`)**
  - `extract_and_serialize_golden_dataset` 함수: 피드백 텍스트뿐만 아니라 `session_id`, `message_id`를 활용해 실제 `ChatHistory`와 조인하여 컨텍스트 보강.

## 🟡 [P3] Phase 4: MCP & Obsidian Sync 실시간 연동
외부 에이전트 및 로컬 에디터와의 동기화 완결성을 위한 작업입니다.

- [ ] **Obsidian Sync Logic (`backend/mcp/obsidian_server.py`)**
  - 실제 파일 동기화(Sync) 로직 및 내부 DB 해시와 대조(Match)하는 핵심 비교 엔진 구현.
- [ ] **Persistent Embeddings (`backend/mcp/server.py` & `backend/celery_app/tasks/graph.py`)**
  - 임베딩 메모리 로드 방식을 DB/Cache 기반 영구 로딩(Persistent loading) 로직으로 교체 (`FAISSRetriever` 활용).
- [ ] **Sync Status API (`backend/api/endpoints/sync.py`)**
  - `get_sync_status`, `get_mcp_status`, `get_conflicts` 등: 상태 응답을 `SyncMapManager`, `ExternalSyncLog` 등의 실제 매니저/DB에서 동적으로 조회하도록 연결.

## 🟢 [P4] 기타: Dashboard & Metadata (MVP 이후)
운영 가시성 및 사용자 부가 정보 제공 영역입니다.

- [ ] **Dashboard Stats (`backend/api/endpoints/automation.py`)**
  - `get_dashboard_summary`, `get_watchdog_events` 함수: 임시 수치 대신 실제 로그와 시스템 지표 집계 로직 반영.
- [ ] **Metadata API (`backend/api/endpoints/metadata.py`)**
  - `get_metadata`, `update_metadata` 함수: 파일 메타데이터의 실제 조회 및 업데이트 기능 연동.
- [ ] **Reporting Task (`backend/celery_app/tasks/reporting.py`)**
  - 파일 파싱 등 메모리 위주의 작업을 추후 DB 쿼리 기반으로 성능 개선(최적화).

---
*💡 관리 가이드: 해결된 항목은 본 문서에서 체크표시(`[x]`) 처리하고, 실제 소스 코드 상의 주석을 제거하여 단일 진실 공급원(SSOT)을 유지합니다.*
*✅ 최종 싱크 점검: 코드베이스의 `# TODO` 주석과 본 문서의 항목이 일치함을 확인 (점검일: 2026-06-25). 💡 참고: TODO 항목의 개수는 개발 과정에 따라 수시로 변동(drift)될 수 있으므로, 주기적인 정합성 점검을 권장합니다.*

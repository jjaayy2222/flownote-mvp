# FlowNote MVP - TODO & FIXME 추적 문서

본 문서는 코드베이스 전반에 산재되어 있는 `TODO` 및 `FIXME` 주석들을 중앙에서 추적하고 관리하기 위해 생성되었습니다.

## 🔴 [P1] Phase 2: Authentication & Core DB 연동
보안 및 핵심 데이터 무결성과 직결되므로 최우선으로 해결해야 할 부채입니다.

- [x] **Authentication (`backend/api/deps.py`)**
  - `get_current_user` 및 `get_current_user_ws` 함수: 현재 Mock 사용 중인 부분을 `verify_token(token)` 기반 실제 JWT 인증 로직으로 대체 (PyJWT 기반 서명/만료시간 검증).
  - 전역 의존성을 `backend.config.AppConfig` 및 `AuthConfig`를 통해 라우팅하도록 개선.
  - [x] `deps.py` 1차 개선: JWT 시크릿 강도 검증(최소 32자/취약값 거부), WebSocket URL 쿼리 토큰 노출 차단(헤더 전용 인증), 토큰 발급 엔드포인트(`/api/auth/token`, `/token`) 추가 및 WebSocket 로그 PII 마스킹.
  - [x] `deps.py` 2차 개선: JWT 시크릿 플레이스홀더 대소문자 무관 검사, RFC 7518 §3.2 기반 HMAC 알고리즘별 최소 키 길이(HS256: 32자, HS384: 48자, HS512: 64자) 동적 검증 및 'none' 알고리즘 차단, WebSocket 연결 종료 사유(reason) 정제(CWE-117 로그 인젝션 및 PII 차단).
- [ ] **Sync DB (`backend/services/sync_service.py`)**
  - `_handle_conflict` 메서드: 충돌 발생 시 DB에 충돌 레코드를 영구 저장하는 로직.
- [x] **Conflict Resolution (`backend/services/conflict_resolution_service.py`)**
  - 파일 시스템(JSONL) 안전 기록 및 `PathConfig` 활용 보완.

## 🟠 [P2] Phase 3: Automation & Scheduler 구현
자동화 작업의 실질적인 동작과 데이터 신뢰성을 보장하는 항목입니다.

- [ ] **Automation Rules DB 연동 (`backend/services/automation_manager.py`)**
  - `get_automation_rules`, `create_automation_rule` 등 규칙 CRUD 전체 메서드: 파일/Mock 기반에서 DB 연동으로 전환 (현재 JSONL은 임시 스토리지로, 재배포/다중 인스턴스 환경을 위해 DB 마이그레이션 필수).
- [ ] **Celery 연동 (`backend/api/endpoints/automation.py`)**
  - `trigger_automation_task` 엔드포인트: 실제 Celery 태스크 지연 실행(`task.delay()`) 트리거 활성화.
- [x] **Golden Dataset 조인 (`backend/services/scheduler_service.py`)**
  - `extract_and_serialize_golden_dataset` 함수: 피드백 텍스트뿐만 아니라 `session_id`, `message_id`를 활용해 실제 `ChatHistory`와 조인하여 컨텍스트 보강 (1차 연동 및 세션 캐시, PathConfig 기반 SSOT 적용).

## 🟡 [P3] Phase 4: MCP & Obsidian Sync 실시간 연동
외부 에이전트 및 로컬 에디터와의 동기화 완결성을 위한 작업입니다.

- [ ] **Obsidian Sync Logic (`backend/mcp/obsidian_server.py`)**
  - 실제 파일 동기화(Sync) 로직 및 내부 DB 해시와 대조(Match)하는 핵심 비교 엔진 구현.
- [ ] **Persistent Embeddings (`backend/mcp/server.py`, `backend/celery_app/tasks/graph.py`, `backend/celery_app/tasks/classification.py`)**
  - 임베딩 메모리 로드 방식을 DB/Cache 기반 영구 로딩(Persistent loading) 로직으로 교체 (`FAISSRetriever` 활용).
  - 분류 결과 기반 임베딩 업데이트 로직 추가 구현 필요.
- [ ] **Sync Status API (`backend/api/endpoints/sync.py`)**
  - `get_sync_status`, `get_mcp_status`, `get_conflicts` 등: 상태 응답을 `SyncMapManager`, `ExternalSyncLog` 등의 실제 매니저/DB에서 동적으로 조회하도록 연결.
  - [x] `get_conflict_diff`, `resolve_conflict`: Mock 데이터를 제거하고 데이터베이스에서 diff 경로를 조회 및 실제 ConflictResolutionService를 연동하여 충돌 해결을 트리거 (JSONL 로그 연동 완료).
  - [x] `get_conflict_diff` 1차 개선: 로컬/원격 파일 사용 불가 시 빈 문자열 대신 422 오류 반환 — 유효한 빈 파일과 사용 불가 상태를 명확히 구분. `test_diff_viewer_flow.py`도 함께 수정.
  - [x] `get_conflict_diff` 2차 개선: `UnicodeDecodeError` 처리 추가 — 잘못된 UTF-8 파일을 500 대신 422로 반환. `ObsidianSyncService.pull_file()`도 동일하게 일관성 확보.
  - [x] `get_conflicts` 실연동: `detected_conflicts.jsonl` JSONL 파일 기반 실제 충돌 이력 반환으로 Mock 제거 — 최신순 정렬, status 필터링, 파싱 에러 카운터 집계 로그 적용.


## 🟢 [P4] 기타: Dashboard & Metadata (MVP 이후)
운영 가시성 및 사용자 부가 정보 제공 영역입니다.

- [ ] **Dashboard Stats (`backend/api/endpoints/automation.py`)**
  - `get_dashboard_summary`, `get_watchdog_events` 함수: 임시 수치 대신 실제 로그와 시스템 지표 집계 로직 반영.
  - [x] `get_watchdog_events` 실연동: `events.jsonl` 파일 기반 실제 Watchdog 이벤트 이력 반환으로 하드코딩 더미 제거 — 최신순 정렬, `event_type` 필터링, 파싱 에러 집계 및 PII 안전 처리.
  - [x] `get_watchdog_events` 1차 개선: `event_type` 쿼리 파라미터 `Literal` 유효성 검사(422) 및 동일 타임스탬프 발생 시 파일 추가 순서 기반 2차 보조 정렬(`line_num` 내림차순) 적용.
  - [x] `get_watchdog_events` 2차 개선: Sourcery 리팩토링 반영 — `_parse_watchdog_event_line` 서브 헬퍼 분리(복잡도 해소), 규칙 CRUD 예외 체이닝(`raise ... from exc`) 및 집계 표현식 단순화.
- [x] **Metadata API (`backend/api/endpoints/metadata.py`)**
  - `get_metadata`, `update_metadata` 함수: 파일 메타데이터의 실제 조회 및 업데이트 기능 연동 (FileMetadata 및 PathConfig SSOT 결합, 미존재 시 404 오류 처리, 영속화 실패 시 롤백 및 PII 안전 로깅 적용).
- [ ] **Reporting Task (`backend/celery_app/tasks/reporting.py`)**
  - 파일 파싱 등 메모리 위주의 작업을 추후 DB 쿼리 기반으로 성능 개선(최적화).

---
*💡 관리 가이드: 해결된 항목은 본 문서에서 체크표시(`[x]`) 처리하고, 실제 소스 코드 상의 주석을 제거하여 단일 진실 공급원(SSOT)을 유지합니다.*
- **✅ 코드베이스 싱크 상태**: `# TODO` 주석과 본 문서의 항목이 정확히 일치함을 확인했습니다. (마지막 점검일: 2026-10-18)
- **💡 변동성(Drift) 주의**: TODO 항목의 개수나 내용은 개발 과정에 따라 수시로 변동될 수 있으므로, 주기적인 정합성 점검을 권장합니다.

# FlowNote MVP - TODO & FIXME 추적 문서

본 문서는 코드베이스 전반에 산재되어 있는 `TODO` 및 `FIXME` 주석들을 중앙에서 추적하고 관리하기 위해 생성되었습니다.

## 🛠 Backend API & Deps
- [ ] `backend/api/deps.py` (L46): `Route this through backend.config.AppConfig when available.`
- [ ] `backend/api/deps.py` (L65, L91): `[Phase 2] verify_token(token)` 로직 구현 필요
- [ ] `backend/api/endpoints/metadata.py` (L19, L34): 실제 메타데이터 조회 및 업데이트 기능 구현
- [ ] `backend/api/endpoints/automation.py` (L202): Celery 태스크 트리거 구현
- [ ] `backend/api/endpoints/automation.py` (L250): 실제로는 파일 시스템 또는 DB에서 조회하도록 변경
- [ ] `backend/api/endpoints/automation.py` (L301): 실제 데이터 집계 로직 구현
- [ ] `backend/api/endpoints/sync.py` (L114): 실제 `last_sync`는 `SyncMapManager`에서 조회하도록 연동
- [ ] `backend/api/endpoints/sync.py` (L137, L143, L144): 실제 MCP 서버 상태 및 클라이언트 목록 연동
- [ ] `backend/api/endpoints/sync.py` (L176): `ExternalSyncLog`에서 충돌 이력 조회 연동
- [ ] `backend/api/endpoints/sync.py` (L195): DB에서 `conflict_id`로 경로 정보 조회 연동
- [ ] `backend/api/endpoints/sync.py` (L232): `ConflictResolutionService`를 통해 실제 충돌 해결 연동

## ⚙️ Backend Services & Managers
- [ ] `backend/services/scheduler_service.py` (L43): 차후에 `session_id`와 `message_id`를 통해 실제 `ChatHistory`와 조인
- [ ] `backend/services/sync_service.py` (L164): DB에 충돌 레코드 저장
- [ ] `backend/services/automation_manager.py` (L123, L140, L160, L177): DB 연동 후 실제 규칙 조회/저장/수정/삭제 구현
- [ ] `backend/services/conflict_resolution_service.py` (L244): JSONL 파일에 기록 (`PathConfig` 사용)

## 🔄 Celery Tasks & MCP
- [ ] `backend/celery_app/tasks/reporting.py` (L74): 추후 DB 쿼리로 개선 권장
- [ ] `backend/celery_app/tasks/graph.py` (L93): DB/캐시에서 임베딩 로드 로직으로 교체
- [ ] `backend/mcp/obsidian_server.py` (L143): 실제 동기화(sync) 로직 구현
- [ ] `backend/mcp/obsidian_server.py` (L153): 내부 DB 해시와 대조(Match)하는 로직 구현
- [ ] `backend/mcp/server.py` (L57): 임베딩의 영구적 로딩(Persistent loading) 구현 (`FAISSRetriever` 등에서)

---
*참고: 이미 해결된 `TODO` 항목이 있다면 본 문서에서 체크표시(`[x]`) 후 소스 코드 내의 주석은 제거해 주시면 됩니다.*

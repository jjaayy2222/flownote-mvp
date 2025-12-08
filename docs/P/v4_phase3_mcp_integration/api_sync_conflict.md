# Sync & Conflict Resolution API 문서

**Version**: v4.0 Phase 3  
**Last Updated**: 2025-12-08  
**Base URL**: `/api/sync`

---

## 📋 목차

- [Sync \& Conflict Resolution API 문서](#sync--conflict-resolution-api-문서)
  - [📋 목차](#-목차)
  - [개요](#개요)
    - [주요 기능](#주요-기능)
    - [지원 도구](#지원-도구)
  - [인증](#인증)
  - [API 엔드포인트](#api-엔드포인트)
    - [POST /sync/trigger](#post-synctrigger)
    - [GET /sync/status](#get-syncstatus)
    - [GET /sync/conflicts](#get-syncconflicts)
    - [POST /sync/conflicts/{conflict\_id}/resolve](#post-syncconflictsconflict_idresolve)
  - [데이터 모델](#데이터-모델)
    - [SyncConflict](#syncconflict)
    - [ResolutionStrategy](#resolutionstrategy)
    - [ConflictResolution](#conflictresolution)
  - [사용 예제](#사용-예제)
    - [전체 워크플로우](#전체-워크플로우)
  - [에러 처리](#에러-처리)
    - [공통 에러 응답 형식](#공통-에러-응답-형식)
    - [에러 코드 정리](#에러-코드-정리)
  - [제한사항 (MVP)](#제한사항-mvp)
  - [향후 계획](#향후-계획)
    - [Phase 4](#phase-4)
    - [Phase 5](#phase-5)
  - [참고 문서](#참고-문서)

---

## 개요

FlowNote v4.0 Phase 3에서는 **MCP (Model Context Protocol)** 기반의 외부 도구 동기화 기능을 제공합니다. 현재 MVP에서는 **Obsidian**만 지원하며, 양방향 동기화 및 충돌 해결 기능을 포함합니다.

### 주요 기능

- ✅ **수동 동기화 트리거**: Obsidian Vault 전체 파일 동기화
- ✅ **동기화 상태 조회**: 연결 상태, 감시 상태, 매핑 개수 확인
- ✅ **충돌 감지**: Content Mismatch, File Deleted 등 자동 감지
- ✅ **충돌 해결**: 전략 기반 해결 (Auto, Manual)

### 지원 도구

| 도구 | 상태 | 비고 |
|------|------|------|
| Obsidian | ✅ 지원 | MVP 구현 완료 |
| Notion | 🚧 계획 | Phase 4 예정 |
| Google Drive | 🚧 계획 | Phase 5 예정 |

---

## 인증

현재 MVP에서는 별도 인증이 필요하지 않습니다.  
**TODO**: Phase 4에서 사용자별 동기화 설정 지원 예정.

---

## API 엔드포인트

### POST /sync/trigger

**설명**: Obsidian Vault 전체 파일에 대한 수동 동기화를 트리거합니다.

**Request**

```http
POST /api/sync/trigger
Content-Type: application/json
```

**Request Body**: 없음 (MVP에서는 Obsidian 전체 동기화만 지원)

**Response** (202 Accepted)

```json
{
  "message": "Sync triggered successfully",
  "tool_type": "OBSIDIAN",
  "conflicts_detected": 2,
  "conflicts": [
    {
      "conflict_id": "uuid-1234",
      "file_id": "file-001",
      "external_path": "/vault/note.md",
      "tool_type": "OBSIDIAN",
      "conflict_type": "CONTENT_MISMATCH",
      "local_hash": "abc123",
      "remote_hash": "def456",
      "status": "PENDING",
      "detected_at": "2025-12-08T17:00:00Z"
    }
  ]
}
```

**cURL 예제**

```bash
curl -X POST http://localhost:8000/api/sync/trigger \
  -H "Content-Type: application/json"
```

**Python 예제**

```python
import requests

response = requests.post("http://localhost:8000/api/sync/trigger")
data = response.json()

print(f"Conflicts detected: {data['conflicts_detected']}")
for conflict in data['conflicts']:
    print(f"- {conflict['external_path']}: {conflict['conflict_type']}")
```

**에러 응답**

| Status Code | 설명 |
|-------------|------|
| 503 | Obsidian Vault 연결 실패 |
| 501 | 동기화 기능 미구현 (일부 기능) |
| 500 | 서버 내부 오류 |

---

### GET /sync/status

**설명**: 현재 동기화 상태를 조회합니다.

**Request**

```http
GET /api/sync/status
```

**Response** (200 OK)

```json
{
  "tool_type": "OBSIDIAN",
  "is_connected": true,
  "is_watching": true,
  "last_sync_at": null,
  "total_mappings": 42
}
```

**Response Fields**

| Field | Type | 설명 |
|-------|------|------|
| `tool_type` | string | 외부 도구 타입 (현재: "OBSIDIAN") |
| `is_connected` | boolean | Vault 연결 상태 |
| `is_watching` | boolean | 파일 감시 활성화 여부 |
| `last_sync_at` | string\|null | 마지막 동기화 시각 (TODO) |
| `total_mappings` | integer | 현재 매핑된 파일 개수 |

**cURL 예제**

```bash
curl http://localhost:8000/api/sync/status
```

**Python 예제**

```python
import requests

response = requests.get("http://localhost:8000/api/sync/status")
status = response.json()

if status['is_connected']:
    print(f"✅ Connected to {status['tool_type']}")
    print(f"📊 Total mappings: {status['total_mappings']}")
else:
    print("❌ Not connected")
```

---

### GET /sync/conflicts

> **⚠️ MVP 제한사항**: DB 저장 없이 **실시간 스캔 결과만 반환**합니다. 매 호출마다 전체 Vault를 스캔하므로 성능 이슈가 있을 수 있습니다.

**설명**: 현재 감지된 충돌 목록을 조회합니다.

**Request**

```http
GET /api/sync/conflicts
```

**Response** (200 OK)

```json
{
  "conflicts": [
    {
      "conflict_id": "uuid-1234",
      "file_id": "file-001",
      "external_path": "/vault/note.md",
      "tool_type": "OBSIDIAN",
      "conflict_type": "CONTENT_MISMATCH",
      "local_hash": "abc123",
      "remote_hash": "def456",
      "status": "PENDING",
      "detected_at": "2025-12-08T17:00:00Z"
    }
  ],
  "total_count": 1
}
```

**cURL 예제**

```bash
curl http://localhost:8000/api/sync/conflicts
```

**Python 예제**

```python
import requests

response = requests.get("http://localhost:8000/api/sync/conflicts")
data = response.json()

print(f"Total conflicts: {data['total_count']}")
for conflict in data['conflicts']:
    print(f"- {conflict['external_path']}: {conflict['conflict_type']}")
```

**Note**: MVP에서는 DB 저장 없이 실시간 스캔 결과만 반환합니다.  
**TODO**: 충돌 캐싱으로 반복 스캔 비용 절감 필요.

---

### POST /sync/conflicts/{conflict_id}/resolve

> **⚠️ MVP 제한사항**: 현재 File Service 미구현으로 인해 **모든 해결 시도가 `FAILED` 상태로 반환**됩니다. 실제 파일 쓰기 동작은 Phase 4에서 구현 예정입니다.

**설명**: 특정 충돌을 해결합니다.

**Request**

```http
POST /api/sync/conflicts/{conflict_id}/resolve
Content-Type: application/json
```

**Path Parameters**

| Parameter | Type | 설명 |
|-----------|------|------|
| `conflict_id` | string | 해결할 충돌 ID |

**Request Body**

```json
{
  "strategy": {
    "method": "AUTO_BY_CONTEXT",
    "recommended_value": null,
    "confidence": 0.9,
    "reasoning": "Remote wins strategy",
    "conflict_id": "uuid-1234"
  }
}
```

**Resolution Methods**

| Method | 설명 | 상태 |
|--------|------|------|
| `MANUAL_OVERRIDE` | 사용자가 직접 선택한 내용 사용 | 🚧 미구현 |
| `AUTO_BY_CONTEXT` | 컨텍스트 기반 자동 해결 (MVP: Remote Wins) | ✅ 구현 |
| `AUTO_BY_CONFIDENCE` | 신뢰도 기반 자동 해결 (MVP: Remote Wins) | ✅ 구현 |

**Response** (200 OK)

```json
{
  "resolution": {
    "conflict_id": "uuid-1234",
    "status": "FAILED",
    "strategy": {
      "method": "AUTO_BY_CONTEXT",
      "recommended_value": null,
      "confidence": 0.9,
      "reasoning": "Remote wins strategy",
      "conflict_id": "uuid-1234"
    },
    "resolved_by": "system",
    "resolved_at": "2025-12-08T17:05:00Z",
    "notes": "Not implemented: File Service required"
  },
  "success": false
}
```

**cURL 예제**

```bash
curl -X POST http://localhost:8000/api/sync/conflicts/uuid-1234/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": {
      "method": "AUTO_BY_CONTEXT",
      "recommended_value": null,
      "confidence": 0.9,
      "reasoning": "Remote wins strategy",
      "conflict_id": "uuid-1234"
    }
  }'
```

**Python 예제**

```python
import requests

conflict_id = "uuid-1234"
payload = {
    "strategy": {
        "method": "AUTO_BY_CONTEXT",
        "recommended_value": None,
        "confidence": 0.9,
        "reasoning": "Remote wins strategy",
        "conflict_id": conflict_id
    }
}

response = requests.post(
    f"http://localhost:8000/api/sync/conflicts/{conflict_id}/resolve",
    json=payload
)

result = response.json()
if result['success']:
    print("✅ Conflict resolved successfully")
else:
    print(f"❌ Resolution failed: {result['resolution']['notes']}")
```

**에러 응답**

| Status Code | 설명 |
|-------------|------|
| 404 | 충돌 ID를 찾을 수 없음 |
| 501 | 해결 전략 미구현 |
| 500 | 서버 내부 오류 |

---

## 데이터 모델

### SyncConflict

```json
{
  "conflict_id": "string (UUID)",
  "file_id": "string",
  "external_path": "string",
  "tool_type": "OBSIDIAN",
  "conflict_type": "CONTENT_MISMATCH | DELETED_REMOTE | DELETED_LOCAL | METADATA_MISMATCH",
  "local_hash": "string | null",
  "remote_hash": "string | null",
  "status": "PENDING | PENDING_REVIEW | RESOLVED | FAILED",
  "detected_at": "string (ISO 8601)",
  "metadata": "object | null"
}
```

**Enum Values**

- **conflict_type**:
  - `CONTENT_MISMATCH`: 로컬/원격 내용 불일치
  - `DELETED_REMOTE`: 원격에서 삭제됨
  - `DELETED_LOCAL`: 로컬에서 삭제됨
  - `METADATA_MISMATCH`: 메타데이터 불일치

- **status**:
  - `PENDING`: 해결 대기 중
  - `PENDING_REVIEW`: 검토 대기 중
  - `RESOLVED`: 해결 완료
  - `FAILED`: 해결 실패

### ResolutionStrategy

```json
{
  "method": "MANUAL_OVERRIDE | AUTO_BY_CONTEXT | AUTO_BY_CONFIDENCE | VOTING | HYBRID",
  "recommended_value": "string | null",
  "confidence": "number (0.0 ~ 1.0)",
  "reasoning": "string",
  "conflict_id": "string (UUID)"
}
```

**Enum Values**

- **method**:
  - `MANUAL_OVERRIDE`: 사용자 수동 선택 (🚧 미구현)
  - `AUTO_BY_CONTEXT`: 컨텍스트 기반 자동 해결 (✅ MVP: Remote Wins)
  - `AUTO_BY_CONFIDENCE`: 신뢰도 기반 자동 해결 (✅ MVP: Remote Wins)
  - `VOTING`: 투표 기반 해결 (🚧 미구현)
  - `HYBRID`: 하이브리드 해결 (🚧 미구현)

### ConflictResolution

```json
{
  "conflict_id": "string (UUID)",
  "status": "RESOLVED | FAILED",
  "strategy": "ResolutionStrategy",
  "resolved_by": "string (user_id or 'system')",
  "resolved_at": "string (ISO 8601)",
  "notes": "string | null"
}
```

---

## 사용 예제

### 전체 워크플로우

```python
import requests

BASE_URL = "http://localhost:8000/api/sync"

# 1. 동기화 상태 확인
status = requests.get(f"{BASE_URL}/status").json()
print(f"Connected: {status['is_connected']}")

# 2. 수동 동기화 트리거
sync_result = requests.post(f"{BASE_URL}/trigger").json()
print(f"Conflicts detected: {sync_result['conflicts_detected']}")

# 3. 충돌 목록 조회
conflicts = requests.get(f"{BASE_URL}/conflicts").json()

# 4. 각 충돌 해결
for conflict in conflicts['conflicts']:
    conflict_id = conflict['conflict_id']
    
    # Auto resolution
    payload = {
        "strategy": {
            "method": "AUTO_BY_CONTEXT",
            "recommended_value": None,
            "confidence": 0.9,
            "reasoning": "Auto resolution",
            "conflict_id": conflict_id
        }
    }
    
    result = requests.post(
        f"{BASE_URL}/conflicts/{conflict_id}/resolve",
        json=payload
    ).json()
    
    print(f"Resolved {conflict_id}: {result['success']}")
```

---

## 에러 처리

### 공통 에러 응답 형식

```json
{
  "detail": "Error message"
}
```

### 에러 코드 정리

| Status Code | 설명 | 대응 방법 |
|-------------|------|----------|
| 202 | 동기화 요청 수락 | 정상 (비동기 처리) |
| 404 | 충돌 ID 없음 | 충돌 목록 재조회 |
| 501 | 기능 미구현 | MVP 제한사항 확인 |
| 503 | Vault 연결 실패 | Obsidian 설정 확인 |
| 500 | 서버 오류 | 로그 확인 및 재시도 |

---

## 제한사항 (MVP)

1. **단일 도구 지원**: Obsidian만 지원 (Notion, Google Drive는 Phase 4-5)
2. **전체 동기화만 지원**: 개별 파일 동기화 미지원
3. **충돌 캐싱 없음**: 매번 실시간 스캔 (성능 이슈 가능)
4. **File Service 미구현**: 실제 파일 쓰기 동작 불가 (Resolution FAILED)
5. **사용자별 설정 없음**: 전역 설정만 사용

---

## 향후 계획

### Phase 4
- [ ] Notion 통합
- [ ] 사용자별 동기화 설정
- [ ] 충돌 DB 저장 및 캐싱
- [ ] 개별 파일 동기화

### Phase 5
- [ ] Google Drive 통합
- [ ] 실시간 양방향 동기화
- [ ] 충돌 해결 UI
- [ ] 동기화 히스토리

---

## 참고 문서

- [MCP 설정 가이드](../../config/mcp_config.md)
- [테스트 결과](./test_result_obsidian_sync.txt)

---

> **작성자**: Jay 
> 
> **문의**: GitHub Issues

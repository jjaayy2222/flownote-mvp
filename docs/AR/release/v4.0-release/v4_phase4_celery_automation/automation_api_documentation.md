# Automation API 문서

**Version**: v4.0 Phase 4  
**Last Updated**: 2025-12-16  
**Base URL**: `/api/automation`

---

## 📋 목차

- [Automation API 문서](#automation-api-문서)
  - [📋 목차](#-목차)
  - [개요](#개요)
    - [주요 기능](#주요-기능)
    - [자동화 작업 유형](#자동화-작업-유형)
  - [인증](#인증)
  - [API 엔드포인트](#api-엔드포인트)
    - [GET /automation/logs](#get-automationlogs)
    - [GET /automation/logs/{log\_id}](#get-automationlogslog_id)
    - [GET /automation/rules](#get-automationrules)
    - [POST /automation/rules](#post-automationrules)
    - [PUT /automation/rules/{rule\_id}](#put-automationrulesrule_id)
    - [DELETE /automation/rules/{rule\_id}](#delete-automationrulesrule_id)
    - [GET /automation/reclassifications](#get-automationreclassifications)
    - [GET /automation/archives](#get-automationarchives)
    - [POST /automation/tasks/trigger](#post-automationtaskstrigger)
  - [데이터 모델](#데이터-모델)
    - [AutomationTaskType](#automationtasktype)
    - [AutomationStatus](#automationstatus)
    - [AutomationLog](#automationlog)
    - [AutomationRule](#automationrule)
    - [ReclassificationRecord](#reclassificationrecord)
    - [ArchivingRecord](#archivingrecord)
  - [Celery Beat 스케줄](#celery-beat-스케줄)
  - [사용 예제](#사용-예제)
    - [전체 워크플로우](#전체-워크플로우)
  - [에러 처리](#에러-처리)
    - [공통 에러 응답 형식](#공통-에러-응답-형식)
    - [에러 코드 정리](#에러-코드-정리)
  - [제한사항 (MVP)](#제한사항-mvp)
  - [향후 계획](#향후-계획)
  - [참고 문서](#참고-문서)

---

## 개요

FlowNote v4.0 Phase 4에서는 **Celery 기반 자동화 시스템**을 제공합니다. PARA 방법론의 순환성을 구현하기 위해 재분류, 아카이브, 리포트 생성 등의 작업을 자동으로 실행합니다.

### 주요 기능

- ✅ **자동화 로그 조회**: 실행된 자동화 작업의 로그 및 상태 확인
- ✅ **재분류 이력**: 파일 재분류 기록 조회
- ✅ **아카이브 이력**: 파일 아카이빙 기록 조회
- 🚧 **규칙 관리**: 사용자 정의 자동화 규칙 (DB 연동 필요)
- 🚧 **수동 트리거**: 자동화 작업 수동 실행 (Celery 연동 필요)

### 자동화 작업 유형

| 작업 유형 | 설명 | 스케줄 |
|----------|------|--------|
| `reclassification` | PARA 카테고리 재분류 | 매일 00:00, 매주 일요일 00:00 |
| `archiving` | 비활성 파일 자동 아카이브 | 매주 일요일 02:00 |
| `reporting` | 주간/월간 리포트 생성 | 매주 월요일 08:00, 매월 1일 10:00 |
| `monitoring` | 동기화 상태 확인 | 매 10분 |
| `maintenance` | 로그 정리 등 유지보수 | 매일 03:00 |

---

## 인증

현재 MVP에서는 별도 인증이 필요하지 않습니다.  
**TODO**: 향후 사용자별 자동화 설정 지원 예정.

---

## API 엔드포인트

### GET /automation/logs

**설명**: 자동화 작업 로그 목록을 조회합니다.

**Request**

```http
GET /api/automation/logs?limit=100&task_type=reclassification&status=completed
```

**Query Parameters**

| Parameter | Type | Required | 설명 |
|-----------|------|----------|------|
| `limit` | integer | No | 최대 반환 개수 (기본값: 100, 범위: 1-1000) |
| `task_type` | AutomationTaskType | No | 작업 유형 필터 |
| `status` | AutomationStatus | No | 상태 필터 |

**Response** (200 OK)

```json
{
  "total": 42,
  "logs": [
    {
      "log_id": "550e8400-e29b-41d4-a716-446655440000",
      "task_type": "reclassification",
      "task_name": "daily-reclassify",
      "celery_task_id": "celery-task-123",
      "status": "completed",
      "files_processed": 150,
      "files_updated": 23,
      "files_archived": 0,
      "errors_count": 2,
      "details": {
        "categories_changed": {
          "Project -> Archive": 15,
          "Resource -> Archive": 8
        }
      },
      "started_at": "2025-12-16T00:00:00+09:00",
      "completed_at": "2025-12-16T00:05:23+09:00",
      "duration_seconds": 323.5
    }
  ]
}
```

**cURL 예제**

```bash
curl "http://localhost:8000/api/automation/logs?limit=10&task_type=reclassification"
```

**Python 예제**

```python
import requests

response = requests.get(
    "http://localhost:8000/api/automation/logs",
    params={
        "limit": 10,
        "task_type": "reclassification",
        "status": "completed"
    }
)

data = response.json()
print(f"Total logs: {data['total']}")
for log in data['logs']:
    print(f"- {log['task_name']}: {log['files_processed']} files processed")
```

---

### GET /automation/logs/{log_id}

**설명**: 특정 자동화 로그의 상세 정보를 조회합니다.

**Request**

```http
GET /api/automation/logs/550e8400-e29b-41d4-a716-446655440000
```

**Path Parameters**

| Parameter | Type | 설명 |
|-----------|------|------|
| `log_id` | string | 로그 ID (UUID) |

**Response** (200 OK)

```json
{
  "log_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_type": "reclassification",
  "task_name": "daily-reclassify",
  "celery_task_id": "celery-task-123",
  "status": "completed",
  "files_processed": 150,
  "files_updated": 23,
  "files_archived": 0,
  "errors_count": 2,
  "details": {
    "categories_changed": {
      "Project -> Archive": 15,
      "Resource -> Archive": 8
    },
    "errors": [
      {
        "file": "/path/to/file.md",
        "error": "Classification failed"
      }
    ]
  },
  "started_at": "2025-12-16T00:00:00+09:00",
  "completed_at": "2025-12-16T00:05:23+09:00",
  "duration_seconds": 323.5
}
```

**cURL 예제**

```bash
curl http://localhost:8000/api/automation/logs/550e8400-e29b-41d4-a716-446655440000
```

**에러 응답**

| Status Code | 설명 |
|-------------|------|
| 404 | 로그 ID를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

### GET /automation/rules

> **⚠️ MVP 제한사항**: DB 미구현으로 현재 **빈 목록**을 반환합니다.

**설명**: 자동화 규칙 목록을 조회합니다.

**Request**

```http
GET /api/automation/rules
```

**Response** (200 OK)

```json
{
  "total": 0,
  "rules": []
}
```

**Phase 4+ 예상 응답**

```json
{
  "total": 2,
  "rules": [
    {
      "rule_id": "rule-001",
      "name": "Auto-archive old projects",
      "task_type": "archiving",
      "conditions": {
        "inactive_days": 30,
        "category": "Project"
      },
      "actions": {
        "move_to": "Archive"
      },
      "is_active": true,
      "created_at": "2025-12-01T10:00:00+09:00"
    }
  ]
}
```

---

### POST /automation/rules

> **⚠️ MVP 제한사항**: DB 미구현으로 **501 Not Implemented** 응답.

**설명**: 새로운 자동화 규칙을 생성합니다.

**Request**

```http
POST /api/automation/rules
Content-Type: application/json
```

**Request Body**

```json
{
  "rule_id": "rule-002",
  "name": "Weekly resource cleanup",
  "task_type": "archiving",
  "conditions": {
    "inactive_days": 14,
    "category": "Resource"
  },
  "actions": {
    "move_to": "Archive"
  },
  "is_active": true
}
```

**Response** (201 Created - Phase 4+)

```json
{
  "rule_id": "rule-002",
  "name": "Weekly resource cleanup",
  "task_type": "archiving",
  "conditions": {
    "inactive_days": 14,
    "category": "Resource"
  },
  "actions": {
    "move_to": "Archive"
  },
  "is_active": true,
  "created_at": "2025-12-16T10:00:00+09:00"
}
```

**MVP 응답** (501 Not Implemented)

```json
{
  "detail": "Rule creation requires database integration"
}
```

---

### PUT /automation/rules/{rule_id}

> **⚠️ MVP 제한사항**: DB 미구현으로 **501 Not Implemented** 응답.

**설명**: 기존 자동화 규칙을 수정합니다.

**Request**

```http
PUT /api/automation/rules/rule-001
Content-Type: application/json
```

**Request Body**

```json
{
  "rule_id": "rule-001",
  "name": "Updated rule name",
  "task_type": "archiving",
  "conditions": {
    "inactive_days": 45
  },
  "actions": {
    "move_to": "Archive"
  },
  "is_active": false
}
```

**MVP 응답** (501 Not Implemented)

```json
{
  "detail": "Rule update requires database integration"
}
```

---

### DELETE /automation/rules/{rule_id}

> **⚠️ MVP 제한사항**: DB 미구현으로 **501 Not Implemented** 응답.

**설명**: 자동화 규칙을 삭제합니다.

**Request**

```http
DELETE /api/automation/rules/rule-001
```

**MVP 응답** (501 Not Implemented)

```json
{
  "detail": "Rule deletion requires database integration"
}
```

---

### GET /automation/reclassifications

**설명**: 재분류 작업 이력을 조회합니다.

**Request**

```http
GET /api/automation/reclassifications?limit=50
```

**Query Parameters**

| Parameter | Type | Required | 설명 |
|-----------|------|----------|------|
| `limit` | integer | No | 최대 반환 개수 (기본값: 100, 범위: 1-1000) |

**Response** (200 OK)

```json
{
  "total": 23,
  "records": [
    {
      "record_id": "rec-001",
      "automation_log_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_path": "/data/notes/project-alpha.md",
      "old_category": "Project",
      "new_category": "Archive",
      "confidence_score": 0.92,
      "reason": "Inactive for 30+ days",
      "processed_at": "2025-12-16T00:01:15+09:00"
    }
  ]
}
```

**cURL 예제**

```bash
curl "http://localhost:8000/api/automation/reclassifications?limit=20"
```

**Python 예제**

```python
import requests

response = requests.get(
    "http://localhost:8000/api/automation/reclassifications",
    params={"limit": 20}
)

data = response.json()
for record in data['records']:
    print(f"{record['file_path']}: {record['old_category']} -> {record['new_category']}")
```

---

### GET /automation/archives

**설명**: 아카이브 작업 이력을 조회합니다.

**Request**

```http
GET /api/automation/archives?limit=50
```

**Query Parameters**

| Parameter | Type | Required | 설명 |
|-----------|------|----------|------|
| `limit` | integer | No | 최대 반환 개수 (기본값: 100, 범위: 1-1000) |

**Response** (200 OK)

```json
{
  "total": 15,
  "records": [
    {
      "record_id": "arc-001",
      "automation_log_id": "550e8400-e29b-41d4-a716-446655440000",
      "file_path": "/data/notes/old-project.md",
      "archive_path": "/data/archive/2025/12/old-project.md",
      "reason": "inactive_for_30_days",
      "archived_at": "2025-12-16T02:05:00+09:00"
    }
  ]
}
```

**cURL 예제**

```bash
curl "http://localhost:8000/api/automation/archives?limit=10"
```

---

### POST /automation/tasks/trigger

> **⚠️ MVP 제한사항**: Celery 연동 미구현으로 **501 Not Implemented** 응답.

**설명**: 자동화 작업을 수동으로 트리거합니다.

**Request**

```http
POST /api/automation/tasks/trigger?task_type=reclassification
```

**Query Parameters**

| Parameter | Type | Required | 설명 |
|-----------|------|----------|------|
| `task_type` | AutomationTaskType | Yes | 실행할 작업 유형 |

**MVP 응답** (501 Not Implemented)

```json
{
  "detail": "Manual task triggering not implemented yet for reclassification"
}
```

**Phase 4+ 예상 응답** (202 Accepted)

```json
{
  "message": "Task triggered successfully",
  "task_type": "reclassification",
  "celery_task_id": "celery-task-456",
  "log_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

---

## 데이터 모델

### AutomationTaskType

```typescript
enum AutomationTaskType {
  RECLASSIFICATION = "reclassification",  // 재분류
  ARCHIVING = "archiving",                // 자동 아카이빙
  REPORTING = "reporting",                // 리포트 생성
  MONITORING = "monitoring",              // 시스템/동기화 모니터링
  MAINTENANCE = "maintenance"             // 로그 정리 등 유지보수
}
```

### AutomationStatus

```typescript
enum AutomationStatus {
  PENDING = "pending",      // 대기 중
  RUNNING = "running",      // 실행 중
  COMPLETED = "completed",  // 완료
  FAILED = "failed",        // 실패
  SKIPPED = "skipped"       // 건너뜀
}
```

### AutomationLog

```typescript
interface AutomationLog {
  log_id: string;                    // UUID
  task_type: AutomationTaskType;
  task_name: string;                 // e.g., "daily-reclassify"
  celery_task_id: string;
  
  status: AutomationStatus;
  
  // 실행 결과 요약
  files_processed: number;
  files_updated: number;
  files_archived: number;
  errors_count: number;
  
  // 상세 결과 (JSON)
  details?: object;
  
  // 타이밍
  started_at: string;                // ISO 8601
  completed_at?: string;             // ISO 8601
  duration_seconds: number;
}
```

### AutomationRule

```typescript
interface AutomationRule {
  rule_id: string;
  name: string;
  task_type: AutomationTaskType;
  conditions: object;                // 실행 조건 (JSON)
  actions: object;                   // 수행 동작 (JSON)
  is_active: boolean;
  created_at: string;                // ISO 8601
}
```

### ReclassificationRecord

```typescript
interface ReclassificationRecord {
  record_id: string;
  automation_log_id: string;         // 연관된 AutomationLog ID
  file_path: string;
  old_category: string;
  new_category: string;
  confidence_score: number;          // 0.0 ~ 1.0
  reason?: string;
  processed_at: string;              // ISO 8601
}
```

### ArchivingRecord

```typescript
interface ArchivingRecord {
  record_id: string;
  automation_log_id: string;         // 연관된 AutomationLog ID
  file_path: string;
  archive_path: string;
  reason: string;                    // e.g., "inactive_for_30_days"
  archived_at: string;               // ISO 8601
}
```

---

## Celery Beat 스케줄

FlowNote는 다음과 같은 정기 작업을 자동으로 실행합니다:

| 작업 | 스케줄 | 설명 |
|------|--------|------|
| **일일 재분류** | 매일 00:00 | 최근 7일 접근 파일 재분류 |
| **주간 재분류** | 매주 일요일 00:00 | 전체 파일 재분류 |
| **자동 아카이브** | 매주 일요일 02:00 | 30일 이상 비활성 파일 아카이브 |
| **주간 리포트** | 매주 월요일 08:00 | 주간 활동 리포트 생성 |
| **월간 리포트** | 매월 1일 10:00 | 월간 활동 리포트 생성 |
| **동기화 상태 확인** | 매 10분 | MCP 동기화 상태 모니터링 |
| **로그 정리** | 매일 03:00 | 30일 이상 된 로그 정리 |

**Celery Beat 설정 예시** (`backend/celery_app/celery.py`):

```python
app.conf.beat_schedule = {
    'daily-reclassify': {
        'task': 'backend.celery_app.tasks.reclassification.daily_reclassify_all',
        'schedule': crontab(hour=0, minute=0),
    },
    'weekly-reclassify': {
        'task': 'backend.celery_app.tasks.reclassification.weekly_reclassify_all',
        'schedule': crontab(hour=0, minute=0, day_of_week=0),
    },
    # ... 기타 스케줄
}
```

---

## 사용 예제

### 전체 워크플로우

```python
import requests

BASE_URL = "http://localhost:8000/api/automation"

# 1. 최근 자동화 로그 조회
logs = requests.get(f"{BASE_URL}/logs", params={"limit": 10}).json()
print(f"Total logs: {logs['total']}")

# 2. 특정 로그 상세 조회
if logs['logs']:
    log_id = logs['logs'][0]['log_id']
    detail = requests.get(f"{BASE_URL}/logs/{log_id}").json()
    print(f"Task: {detail['task_name']}")
    print(f"Status: {detail['status']}")
    print(f"Duration: {detail['duration_seconds']}s")

# 3. 재분류 이력 조회
reclassifications = requests.get(
    f"{BASE_URL}/reclassifications",
    params={"limit": 20}
).json()

for record in reclassifications['records']:
    print(f"{record['file_path']}: {record['old_category']} -> {record['new_category']}")

# 4. 아카이브 이력 조회
archives = requests.get(
    f"{BASE_URL}/archives",
    params={"limit": 20}
).json()

for record in archives['records']:
    print(f"Archived: {record['file_path']} -> {record['archive_path']}")

# 5. 수동 작업 트리거 (Phase 4+)
# response = requests.post(
#     f"{BASE_URL}/tasks/trigger",
#     params={"task_type": "reclassification"}
# )
# print(f"Triggered: {response.json()}")
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
|-------------|------|-----------|
| 200 | 정상 응답 | - |
| 201 | 리소스 생성 성공 | - |
| 202 | 비동기 작업 수락 | 로그 조회로 상태 확인 |
| 204 | 삭제 성공 (응답 본문 없음) | - |
| 404 | 리소스를 찾을 수 없음 | ID 확인 또는 목록 재조회 |
| 501 | 기능 미구현 | MVP 제한사항 확인 |
| 500 | 서버 내부 오류 | 로그 확인 및 재시도 |

---

## 제한사항 (MVP)

1. **규칙 관리 미구현**: DB 연동 필요 (현재 빈 목록 반환)
2. **수동 트리거 미구현**: Celery 연동 필요 (501 응답)
3. **로그 저장소**: JSONL 파일 기반 (DB 전환 예정)
4. **실시간 스캔**: 매 호출마다 파일 읽기 (캐싱 없음)
5. **사용자별 설정 없음**: 전역 설정만 사용

---

## 향후 계획

- [ ] **DB 연동**: AutomationRule, AutomationLog DB 저장
- [ ] **수동 트리거**: Celery 태스크 수동 실행 API
- [ ] **로그 캐싱**: 반복 스캔 비용 절감
- [ ] **사용자별 설정**: 개인화된 자동화 규칙
- [ ] **웹훅 지원**: 작업 완료 시 알림
- [ ] **대시보드**: 자동화 작업 모니터링 UI

---

## 참고 문서

- [Phase 4 워크플로우](../../../temp/2025_12/12_10/files/v1/phase4_workflow.md)
- [Celery 설정 가이드](./celery_setup_guide.md) (예정)
- [자동화 모델 스키마](../../../backend/models/automation.py)

---

> **작성자**: Jay  
> **문의**: GitHub Issues

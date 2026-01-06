# Phase 6: Frontend - Sync Monitor

## 📋 Overview

Phase 6에서는 Phase 5에서 구축한  MCP 서버 및 Obsidian 동기화 상태를 시각화하는 React 기반 Frontend를 구현합니다.

## 🎯 구현 내용

### **2.1 Sync Monitor UI**

- **Obsidian 연결 상태**
  - Status: Connected / Disconnected
  - Vault Path
  - Last Sync 시간
  - File Count
  - Sync Interval
  - 활성화 여부

- **MCP Server 상태**
  - Running / Stopped 상태
  - Active Clients (예: Claude Desktop)
  - Registered Tools 목록
  - Registered Resources 목록

- **충돌 로그 뷰어**
  - 충돌 이력 표시
  - Conflict ID, Type, Status
  - Local/Remote Hash
  - Resolution Method
  - 실시간 업데이트 (5초 polling)

## 🏗️ 아키텍처

```
Frontend (React)
    ↓ HTTP
Backend FastAPI
    ├─ GET /api/sync/status      - Obsidian 상태
    ├─ GET /api/sync/mcp/status  - MCP 서버 상태
    ├─ GET /api/sync/conflicts   - 충돌 이력
    └─ POST /api/sync/conflicts/{id}/resolve - 충돌 해결
```

## 📂 파일 구조

```
backend/api/endpoints/
└── sync.py                 # Sync API endpoints

web_ui/src/
├── components/
│   ├── SyncMonitor.js      # 메인 모니터 컴포넌트
│   └── SyncMonitor.css     # 스타일
└── App.js                  # 앱 통합
```

## 🚀 Running

### Backend
```bash
cd /Users/jay/ICT-projects/flownote-mvp
pyenv activate myenv
python -m uvicorn backend.main:app --reload
# → http://localhost:8000
```

### Frontend
```bash
cd web_ui
npm start
# → http://localhost:3000
```

## 🧪 Testing

### Manual Test
1. Start Backend server
2. Start Frontend
3. Navigate to `http://localhost:3000`
4. Verify:
   - Obsidian status displays correctly
   - MCP status shows tools and resources
   - Conflict history (empty initially)
   - Auto-refresh every 5 seconds

### API Test
```bash
# Sync status
curl http://localhost:8000/api/sync/status

# MCP status
curl http://localhost:8000/api/sync/mcp/status

# Conflicts
curl http://localhost:8000/api/sync/conflicts
```

## 📊 Features

### 현재 구현 (v1)
- ✅ Obsidian 연결 상태 표시
- ✅ MCP 서버 상태 표시
- ✅ 충돌 이력 뷰어
- ✅ 실시간 polling (5초)
- ✅ 반응형 디자인
- ✅ 로딩 및 에러 상태 처리

### 향후 계획 (v2)
- [ ] WebSocket 실시간 업데이트
- [ ] Conflict Diff Viewer
- [ ] Manual conflict resolution UI
- [ ] Sync history chart
- [ ] File operation logs

## 🎨 Design

- **Color Scheme**
  - Connected: Green (#27ae60)
  - Disconnected: Red (#e74c3c)
  - Running: Green
  - Stopped: Red
  - Badges: Blue (#3498db), Purple (#9b59b6)

- **Layout**
  - Responsive grid
  - Card-based design
  - Hover effects
  - Smooth transitions

## 🔗 Related

- [Phase 5 Detail](../temp/2025_12/12_17/files/v2/v5.0_phase5_detail.md)
- [Phase 6 Detail](../temp/2025_12/12_17/files/v2/v5.0_phase6_frontend_detail.md)
- [Backend API Docs](http://localhost:8000/docs)

## 📝 Notes

- Backend API는 placeholder 데이터 사용 중
- 실제 데이터는 SyncMapManager, ExternalSyncLog 통합 후 사용
- MCP 서버 실행 상태는 추후 실제 체크 로직 추가 필요

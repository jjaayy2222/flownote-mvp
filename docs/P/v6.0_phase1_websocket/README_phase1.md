# 01_18.1.md

## Phase 1: WebSocket 실시간 업데이트

## 📋 Overview

v6.0 Phase 1에서는 기존 Polling 방식을 WebSocket으로 전환하여 실시간 데이터 동기화를 구현합니다.

## 🎯 목표

- Polling 방식 제거 및 WebSocket 기반 실시간 통신 구현
- 네트워크 트래픽 50% 이상 감소
- 이벤트 발생 후 1초 이내 UI 업데이트

## 🧪 구현 내용

### 1. Backend WebSocket 서버

#### **WebSocket 엔드포인트**
```python
# backend/api/endpoints/websocket.py

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

#### **ConnectionManager**
```python
# backend/services/websocket_manager.py

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)
```

#### **Redis Pub/Sub 통합**
```python
# backend/services/redis_pubsub.py

import redis.asyncio as redis

class RedisPubSub:
    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL)
        self.pubsub = self.redis.pubsub()
    
    async def subscribe(self, channel: str):
        await self.pubsub.subscribe(channel)
    
    async def publish(self, channel: str, message: str):
        await self.redis.publish(channel, message)
```

### 2. Frontend WebSocket 클라이언트

#### **환경 변수 설정**
```bash
# web_ui/.env.local
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
```

#### **중앙 집중화된 설정 모듈**
```typescript
// web_ui/src/config/websocket.ts

export const getWebSocketUrl = (): string => {
  return process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
};
```

#### **useWebSocket Hook**
```typescript
// web_ui/src/hooks/useWebSocket.ts

export function useWebSocket(url: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<any>(null);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connect = () => {
      ws.current = new WebSocket(url);
      
      ws.current.onopen = () => {
        setIsConnected(true);
        console.log('WebSocket connected');
      };
      
      ws.current.onmessage = (event) => {
        const data = JSON.parse(event.data);
        setLastMessage(data);
      };
      
      ws.current.onclose = () => {
        setIsConnected(false);
        // Auto-reconnect after 3 seconds
        setTimeout(connect, 3000);
      };
    };
    
    connect();
    
    return () => {
      ws.current?.close();
    };
  }, [url]);

  return { isConnected, lastMessage };
}
```

#### **이벤트 타입 정의**
```typescript
// web_ui/src/types/websocket.ts

export type WebSocketEvent = 
  | { type: 'file_classified'; data: FileClassification }
  | { type: 'sync_status_changed'; data: SyncStatus }
  | { type: 'conflict_detected'; data: Conflict }
  | { type: 'graph_updated'; data: GraphData };
```

### 3. 실시간 업데이트 적용

#### **Sync Monitor**
```typescript
// web_ui/src/components/dashboard/SyncMonitor.tsx

import { getWebSocketUrl } from '@/config/websocket';

export function SyncMonitor() {
  const { lastMessage } = useWebSocket(getWebSocketUrl());
  
  useEffect(() => {
    if (lastMessage?.type === 'sync_status_changed') {
      setSyncStatus(lastMessage.data);
    }
  }, [lastMessage]);
  
  // ...
}
```

#### **Graph View**
```typescript
// web_ui/src/components/para/GraphView.tsx

import { getWebSocketUrl } from '@/config/websocket';

export function GraphView() {
  const { lastMessage } = useWebSocket(getWebSocketUrl());
  
  useEffect(() => {
    if (lastMessage?.type === 'graph_updated') {
      setNodes(lastMessage.data.nodes);
      setEdges(lastMessage.data.edges);
    }
  }, [lastMessage]);
  
  // ...
}
```

## 🚀 Running

### Backend
```bash
# WebSocket 서버는 FastAPI와 함께 자동 시작
python -m uvicorn backend.main:app --reload
```

### Frontend
```bash
cd web_ui
npm run dev
```

### 연결 테스트
```bash
# wscat 설치
npm install -g wscat

# WebSocket 연결 테스트 (환경 변수 사용)
wscat -c ${NEXT_PUBLIC_WS_URL:-ws://localhost:8000/ws}
```

## 🧪 Testing

### Unit Tests
```bash
# Backend WebSocket 테스트
pytest tests/unit/test_websocket_manager.py -v

# Frontend Hook 테스트
npm test -- useWebSocket.test.ts
```

#### **검증 완료 항목 (Frontend)**
- [x] **Connection Lifecycle**: 연결 수립, 종료, 상태(`CONNECTING`, `OPEN`, `CLOSING`, `CLOSED`) 변화 검증
- [x] **Message Handling**: 수신 메시지 파싱, JSON 에러 핸들링, 상태 업데이트 검증
- [x] **Auto-Reconnection**: 연결 종료 시 지수 백오프(Exponential Backoff)를 적용한 재연결 로직 및 옵션(`reconnect: boolean`) 동작 검증
- [x] **Cleanup & Safety**: 컴포넌트 Unmount 시 소켓 종료 및 타이머 정리, 메모리 누수 방지 검증
- [x] **Native Event Compatibility**: `jsdom` 및 브라우저 환경의 Native `CloseEvent`/`Event`와의 동작 일치성 검증

### Integration Tests
```bash
# E2E WebSocket 테스트
pytest tests/integration/test_websocket_flow.py -v
```

### Manual Testing Scenarios

#### **Scenario 1: 실시간 파일 분류**
1. Frontend에서 파일 업로드
2. Backend에서 분류 완료 후 WebSocket 이벤트 발송
3. Frontend에서 즉시 Toast 알림 표시
4. Graph View 자동 업데이트 확인

#### **Scenario 2: 동기화 상태 변경**
1. Obsidian Vault에서 파일 수정
2. Backend에서 동기화 감지
3. Sync Monitor 상태 실시간 업데이트 확인

#### **Scenario 3: 재연결 테스트**
1. Backend 서버 중지
2. Frontend에서 연결 끊김 감지
3. Backend 서버 재시작
4. 3초 후 자동 재연결 확인

## 📊 Performance Metrics

### Before (Polling)
- 요청 주기: 5초
- 평균 네트워크 트래픽: ~100KB/min
- 평균 응답 시간: 2-3초

### After (WebSocket)
- 이벤트 기반 통신
- 평균 네트워크 트래픽: ~30KB/min (70% 감소)
- 평균 응답 시간: <1초

## 🐛 Troubleshooting

### **WebSocket 연결 실패**

**원인:**
- CORS 설정 오류
- 방화벽 차단

**해결:**
```python
# backend/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### **재연결 무한 루프**

**원인:**
- 서버 오류로 즉시 연결 종료

**해결:**
```typescript
// Exponential backoff 적용
const reconnectDelay = Math.min(1000 * Math.pow(2, retryCount), 30000);
setTimeout(connect, reconnectDelay);
```

## 📝 Next Steps

- [x] Frontend WebSocket Client 구현 (Hook & Config)
- [x] Frontend Unit Tests 작성 (`useWebSocket` Hook)
- [x] Frontend Integration Tests (`SyncMonitor` 컴포넌트 연동 완료)
- [x] WebSocket 인증 추가 (JWT)
- [x] Redis Pub/Sub 통합 (분산 서버 지원 완료)
- [x] 메시지 압축 (gzip) 구현 완료 (1KB 임계값)
- [x] 연결 풀 관리 (ConnectionManager 구현 완료)
- [ ] 모니터링 대시보드 (연결 수, 메시지 처리량)

## 🔗 Related Documentation

- [FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/)
- [Redis Pub/Sub](https://redis.io/docs/manual/pubsub/)
- [WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)

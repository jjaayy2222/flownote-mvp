// web_ui/src/types/websocket.ts

/**
 * WebSocket 연결 상태
 * 
 * Native WebSocket readyState와의 매핑:
 * - CONNECTING: WebSocket.CONNECTING (0)
 * - CONNECTED: WebSocket.OPEN (1)
 * - DISCONNECTED: WebSocket.CLOSED (3)
 * - RECONNECTING: 커스텀 상태 (재연결 시도 중)
 * - ERROR: 커스텀 상태 (연결 오류)
 * 
 * @see https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/readyState
 */
export enum WebSocketStatus {
  /** 연결 시도 중 (readyState: 0) */
  CONNECTING = 'CONNECTING',
  
  /** 연결됨 (readyState: 1) */
  CONNECTED = 'CONNECTED',
  
  /** 연결 끊김 (readyState: 3) */
  DISCONNECTED = 'DISCONNECTED',
  
  /** 재연결 시도 중 (커스텀 상태) */
  RECONNECTING = 'RECONNECTING',
  
  /** 오류 발생 (커스텀 상태) */
  ERROR = 'ERROR',
}

/**
 * Native WebSocket readyState 상수
 * SSR 환경에서도 안전하게 사용 가능
 */
export const WS_READY_STATE = {
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3,
} as const;

/**
 * WebSocket readyState 타입
 * 유효한 readyState 값만 허용 (0-3)
 */
export type WebSocketReadyState = typeof WS_READY_STATE[keyof typeof WS_READY_STATE];

/**
 * 유효한 readyState 값들의 Set (동기화 보장)
 * Set<number>로 타입 지정하여 타입 가드에서 number 타입 인수 허용
 */
const VALID_READY_STATES: Set<number> = new Set(Object.values(WS_READY_STATE));

/**
 * readyState가 유효한 값인지 타입 가드
 * WS_READY_STATE에서 값을 파생하여 항상 동기화 유지
 * 
 * unknown 타입을 받아 typeof 체크를 수행하여 범용적으로 사용 가능
 * 
 * @param value - 검증할 값 (any type)
 * @returns 유효한 WebSocketReadyState인 경우 true
 * 
 * @example
 * ```typescript
 * const state = externalLib.getState(); // unknown
 * if (isValidReadyState(state)) {
 *   // state is WebSocketReadyState
 * }
 * ```
 */
export const isValidReadyState = (value: unknown): value is WebSocketReadyState => {
  return typeof value === 'number' && VALID_READY_STATES.has(value);
};

/**
 * Native WebSocket readyState를 WebSocketStatus로 변환
 * 
 * number 타입을 받아 실제 WebSocket API와 호환
 * (ws.readyState는 number 타입으로 반환됨)
 * 
 * @param readyState - WebSocket.readyState 값 (0-3)
 * @returns 해당하는 WebSocketStatus
 * 
 * @example
 * ```typescript
 * // nosemgrep: javascript.lang.security.detect-insecure-websocket
 * // 예시 코드: 실제로는 wss:// 사용 권장
 * const ws = new WebSocket('wss://example.com/ws');
 * const status = mapReadyStateToStatus(ws.readyState);
 * ```
 */
export const mapReadyStateToStatus = (readyState: number): WebSocketStatus => {
  // 런타임 타입 가드: 유효한 readyState 값인지 검증
  if (!isValidReadyState(readyState)) {
    console.error(`[WebSocket] Invalid readyState value: ${readyState}`);
    return WebSocketStatus.ERROR;
  }
  
  // 타입 안전한 switch: exhaustiveness check 보장
  // isValidReadyState 통과 후 readyState는 WebSocketReadyState로 narrowing됨
  switch (readyState) {
    case WS_READY_STATE.CONNECTING:
      return WebSocketStatus.CONNECTING;
    case WS_READY_STATE.OPEN:
      return WebSocketStatus.CONNECTED;
    case WS_READY_STATE.CLOSING:
    case WS_READY_STATE.CLOSED:
      return WebSocketStatus.DISCONNECTED;
  }
  
  // Exhaustiveness check: 모든 케이스가 처리되었음을 TypeScript에 증명
  // 새로운 WS_READY_STATE 값이 추가되면 컴파일 오류 발생
  const _exhaustiveCheck: never = readyState;
  
  // 런타임 안전성: 이 지점에 도달하는 것은 버그이므로 명시적으로 예외를 던진다
  throw new Error(`Unexpected WebSocket readyState: ${_exhaustiveCheck}`);
};

/**
 * 파일 분류 결과 데이터 타입
 */
export interface FileClassification {
  id: string;
  fileName: string;
  category: string;
  confidence: number;
  processedAt: string;
}

/**
 * 동기화 상태 데이터 타입
 */
export interface SyncStatus {
  isSyncing: boolean;
  lastSyncedAt: string | null;
  error: string | null;
  pendingChanges: number;
}

/**
 * 충돌 정보 데이터 타입
 */
export interface Conflict {
  id: string;
  fileId: string;
  baseVersion: string;
  remoteVersion: string;
  localVersion: string;
  timestamp: string;
}

/**
 * 그래프 노드 데이터 타입
 */
export interface GraphNode {
  id: string;
  label: string;
  type: 'project' | 'area' | 'resource' | 'archive' | 'note';
  val: number; // 크기
}

/**
 * 그래프 엣지 데이터 타입
 */
export interface GraphEdge {
  source: string;
  target: string;
  value: number; // 가중치
}

/**
 * 그래프 전체 데이터 타입
 */
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/**
 * WebSocket 이벤트 타입 정의 (Discriminated Union)
 * 서버에서 전송되는 메시지의 구조를 정의합니다.
 */
export type WebSocketEvent = 
  | { type: 'file_classified'; data: FileClassification }
  | { type: 'sync_status_changed'; data: SyncStatus }
  | { type: 'conflict_detected'; data: Conflict }
  | { type: 'graph_updated'; data: GraphData };

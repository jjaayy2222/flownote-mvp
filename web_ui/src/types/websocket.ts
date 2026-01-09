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
 * Native WebSocket readyState를 WebSocketStatus로 변환
 * 
 * @param readyState - WebSocket.readyState 값 (0-3)
 * @returns 해당하는 WebSocketStatus
 * 
 * @example
 * ```typescript
 * const status = mapReadyStateToStatus(ws.readyState);
 * ```
 */
export const mapReadyStateToStatus = (readyState: WebSocketReadyState): WebSocketStatus => {
  switch (readyState) {
    case WS_READY_STATE.CONNECTING:
      return WebSocketStatus.CONNECTING;
    case WS_READY_STATE.OPEN:
      return WebSocketStatus.CONNECTED;
    case WS_READY_STATE.CLOSING:
    case WS_READY_STATE.CLOSED:
      return WebSocketStatus.DISCONNECTED;
  }
};

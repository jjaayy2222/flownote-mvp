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
 * @param value - 검증할 값
 * @returns 유효한 WebSocketReadyState인 경우 true
 */
const isValidReadyState = (value: number): value is WebSocketReadyState => {
  return VALID_READY_STATES.has(value);
};

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
  // 런타임 타입 가드: 느슨한 타입 컨텍스트에서 호출될 수 있음
  // 내부적으로 number로 캐스팅하여 검증
  if (!isValidReadyState(readyState as number)) {
    console.error(`[WebSocket] Invalid readyState value: ${readyState}`);
    return WebSocketStatus.ERROR;
  }
  
  // 타입 안전한 switch: exhaustiveness check 보장
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

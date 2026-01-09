//web_ui/src/config/websocket.ts

/**
 * WebSocket 설정 모듈
 * 
 * 환경 변수를 통해 WebSocket URL을 중앙 집중 관리합니다.
 * 개발/프로덕션 환경에 따라 다른 URL을 사용할 수 있습니다.
 */

/**
 * WebSocket URL 가져오기
 * 
 * @returns WebSocket 서버 URL
 * 
 * @example
 * ```typescript
 * import { getWebSocketUrl } from '@/config/websocket';
 * 
 * const wsUrl = getWebSocketUrl();
 * const ws = new WebSocket(wsUrl);
 * ```
 */
export const getWebSocketUrl = (): string => {
  const url = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws';
  
  // 개발 환경에서 로그 출력
  if (process.env.NODE_ENV === 'development') {
    console.log('[WebSocket Config] Using URL:', url);
  }
  
  return url;
};

/**
 * WebSocket 재연결 설정
 */
export const WEBSOCKET_CONFIG = {
  /** 초기 재연결 지연 시간 (ms) */
  INITIAL_RECONNECT_DELAY: 1000,
  
  /** 최대 재연결 지연 시간 (ms) */
  MAX_RECONNECT_DELAY: 30000,
  
  /** 재연결 시도 횟수 (-1: 무제한) */
  MAX_RECONNECT_ATTEMPTS: -1,
} as const;

/**
 * WebSocket 연결 상태
 */
export enum WebSocketStatus {
  CONNECTING = 'CONNECTING',
  CONNECTED = 'CONNECTED',
  DISCONNECTED = 'DISCONNECTED',
  RECONNECTING = 'RECONNECTING',
  ERROR = 'ERROR',
}

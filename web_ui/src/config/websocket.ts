//web_ui/src/config/websocket.ts

/**
 * WebSocket 설정 모듈
 * 
 * 환경 변수를 통해 WebSocket URL을 중앙 집중 관리합니다.
 * 개발/프로덕션 환경에 따라 다른 URL을 사용할 수 있습니다.
 */

/**
 * 중앙 집중식 로거
 * 환경에 따라 로깅 동작을 제어합니다.
 */
const logger = {
  debug: (message: string, ...args: unknown[]) => {
    if (process.env.NODE_ENV === 'development') {
      console.log(`[WebSocket Config] ${message}`, ...args);
    }
  },
  warn: (message: string, ...args: unknown[]) => {
    console.warn(`[WebSocket Config] ${message}`, ...args);
  },
  error: (message: string, ...args: unknown[]) => {
    console.error(`[WebSocket Config] ${message}`, ...args);
  },
};

/**
 * WebSocket URL 유효성 검사
 * 
 * @param url - 검증할 URL
 * @returns 유효한 경우 true
 */
const isValidWebSocketUrl = (url: string): boolean => {
  try {
    const urlObj = new URL(url);
    return urlObj.protocol === 'ws:' || urlObj.protocol === 'wss:';
  } catch {
    return false;
  }
};

/**
 * 현재 호스트 기반 WebSocket URL 생성
 * 
 * @returns 동적으로 생성된 WebSocket URL
 */
const getWebSocketUrlFromLocation = (): string => {
  if (typeof window === 'undefined') {
    // SSR 환경에서는 기본값 반환
    return 'ws://localhost:8000/ws';
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  
  // 개발 환경에서는 백엔드 포트 사용
  if (process.env.NODE_ENV === 'development') {
    return `${protocol}//${window.location.hostname}:8000/ws`;
  }
  
  // 프로덕션 환경에서는 동일 호스트 사용
  return `${protocol}//${host}/ws`;
};

/**
 * WebSocket URL 가져오기
 * 
 * @returns WebSocket 서버 URL
 * @throws {Error} 프로덕션 환경에서 환경 변수가 설정되지 않은 경우
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
  const envUrl = process.env.NEXT_PUBLIC_WS_URL;
  
  // 환경 변수가 설정된 경우
  if (envUrl) {
    // URL 유효성 검사
    if (!isValidWebSocketUrl(envUrl)) {
      logger.error('Invalid WebSocket URL format:', envUrl);
      logger.warn('Falling back to location-based URL');
      return getWebSocketUrlFromLocation();
    }
    
    logger.debug('Using environment variable URL:', envUrl);
    return envUrl;
  }
  
  // 환경 변수가 없는 경우
  if (process.env.NODE_ENV === 'production') {
    logger.warn('NEXT_PUBLIC_WS_URL not set in production, using location-based URL');
  }
  
  const fallbackUrl = getWebSocketUrlFromLocation();
  logger.debug('Using location-based URL:', fallbackUrl);
  
  return fallbackUrl;
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
 * Native WebSocket readyState를 WebSocketStatus로 변환
 * 
 * @param readyState - WebSocket.readyState 값
 * @returns 해당하는 WebSocketStatus
 */
export const mapReadyStateToStatus = (readyState: number): WebSocketStatus => {
  switch (readyState) {
    case WebSocket.CONNECTING:
      return WebSocketStatus.CONNECTING;
    case WebSocket.OPEN:
      return WebSocketStatus.CONNECTED;
    case WebSocket.CLOSING:
    case WebSocket.CLOSED:
      return WebSocketStatus.DISCONNECTED;
    default:
      return WebSocketStatus.ERROR;
  }
};

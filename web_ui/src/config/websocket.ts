// web_ui/src/config/websocket.ts

import { createLogger } from '@/utils/logger';

/**
 * WebSocket 설정 모듈
 * 
 * 환경 변수를 통해 WebSocket URL을 중앙 집중 관리합니다.
 * 개발/프로덕션 환경에 따라 다른 URL을 사용할 수 있습니다.
 */

const logger = createLogger('WebSocket Config');

/**
 * WebSocket URL 유효성 검사
 * 
 * @param url - 검증할 URL
 * @returns ws:// 또는 wss:// 프로토콜로 시작하는 경우 true
 */
const isValidWebSocketUrl = (url: string): boolean => {
  return /^wss?:\/\//.test(url);
};

/**
 * WebSocket URL 가져오기
 * 
 * 우선순위:
 * 1. NEXT_PUBLIC_WS_URL 환경 변수 (유효성 검사 통과 시)
 * 2. window.location 기반 동적 URL (브라우저 환경)
 * 3. NEXT_PUBLIC_WS_FALLBACK_URL 환경 변수 (SSR 환경)
 * 4. ws://localhost:8000/ws (최종 폴백)
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
  const envUrl = process.env.NEXT_PUBLIC_WS_URL;

  // 1. 환경 변수가 설정되고 유효한 경우
  if (envUrl) {
    if (!isValidWebSocketUrl(envUrl)) {
      logger.error('Invalid WebSocket URL format:', envUrl);
      logger.warn('Falling back to location-based URL');
    } else {
      logger.debug('Using environment variable URL:', envUrl);
      return envUrl;
    }
  } else if (process.env.NODE_ENV === 'production') {
    logger.warn('NEXT_PUBLIC_WS_URL not set in production, using location-based URL');
  }

  // 2. SSR 환경 (window 없음)
  if (typeof window === 'undefined') {
    // SSR 폴백 URL (환경 변수로 설정 가능)
    const ssrFallback = process.env.NEXT_PUBLIC_WS_FALLBACK_URL || 'ws://localhost:8000/ws';
    logger.debug('Using SSR fallback URL:', ssrFallback);
    return ssrFallback;
  }

  // 3. 브라우저 환경 - location 기반 동적 URL
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = process.env.NODE_ENV === 'development'
    ? `${window.location.hostname}:8000`
    : window.location.host;

  const fallbackUrl = `${protocol}//${host}/ws`;
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

// Re-export WebSocket types for convenience
export { WebSocketStatus, mapReadyStateToStatus } from '@/types/websocket';

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
 * @returns 유효한 WebSocket URL인 경우 true
 */
const isValidWebSocketUrl = (url: string): boolean => {
  // 1. 프로토콜 체크
  if (!/^wss?:\/\//.test(url)) {
    return false;
  }
  
  // 2. URL 파싱 및 호스트명 검증
  try {
    const urlObj = new URL(url);
    
    // 호스트명이 비어있으면 유효하지 않음
    if (!urlObj.hostname) {
      return false;
    }
    
    // 3. 프로덕션 환경에서는 WSS만 허용
    if (process.env.NODE_ENV === 'production' && urlObj.protocol === 'ws:') {
      logger.warn('Insecure WebSocket (ws://) detected in production. Use wss:// instead.');
      return false;
    }
    
    return true;
  } catch {
    return false;
  }
};

/**
 * WebSocket URL 가져오기
 * 
 * 우선순위:
 * 1. NEXT_PUBLIC_WS_URL 환경 변수 (유효성 검사 통과 시)
 * 2. window.location 기반 동적 URL (브라우저 환경)
 * 3. NEXT_PUBLIC_WS_FALLBACK_URL 환경 변수 (SSR 환경)
 * 4. ws://localhost:8000/ws (개발 환경 SSR만)
 * 
 * @returns WebSocket 서버 URL
 * @throws {Error} 프로덕션 SSR 환경에서 NEXT_PUBLIC_WS_FALLBACK_URL이 설정되지 않은 경우
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
    const ssrFallback = process.env.NEXT_PUBLIC_WS_FALLBACK_URL;
    
    if (ssrFallback) {
      logger.debug('Using SSR fallback URL:', ssrFallback);
      return ssrFallback;
    }
    
    // 개발 환경에서만 localhost 허용
    if (process.env.NODE_ENV === 'development') {
      // nosemgrep: javascript.lang.security.detect-insecure-websocket
      // 개발 환경 전용: 로컬 개발 서버 연결
      const devFallback = 'ws://localhost:8000/ws';
      logger.debug('Using development SSR fallback URL:', devFallback);
      return devFallback;
    }
    
    // 프로덕션 SSR에서 폴백 URL이 없으면 오류
    logger.error('NEXT_PUBLIC_WS_FALLBACK_URL not set in production SSR environment');
    throw new Error('WebSocket URL configuration required for production SSR');
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
export { WebSocketStatus, mapReadyStateToStatus, type WebSocketReadyState } from '@/types/websocket';

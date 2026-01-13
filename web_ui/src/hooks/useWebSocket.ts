// web_ui/src/hooks/useWebSocket.ts

import { useCallback, useEffect, useRef, useState } from 'react';
import { WEBSOCKET_CONFIG } from '@/config/websocket';
import { WebSocketStatus } from '@/types/websocket';
import { logger } from '@/lib/logger';

/**
 * WebSocket 메시지 타입
 */
export interface WebSocketMessage<T = unknown> {
  type: string;
  data: T;
  timestamp?: number;
}

/**
 * useWebSocket 옵션
 */
export interface UseWebSocketOptions<T = unknown> {
  /** 자동 연결 여부 (기본: true) */
  autoConnect?: boolean;
  /** 재연결 활성화 (기본: true) */
  reconnect?: boolean;
  /** 연결 성공 콜백 */
  onOpen?: () => void;
  /** 연결 종료 콜백 */
  onClose?: () => void;
  /** 에러 콜백 */
  onError?: (error: Event) => void;
  /** 메시지 수신 콜백 */
  onMessage?: (message: WebSocketMessage<T>) => void;
}

/**
 * useWebSocket 반환 타입
 */
export interface UseWebSocketReturn<T = unknown> {
  /** WebSocket 연결 상태 */
  status: WebSocketStatus;
  /** 연결 여부 */
  isConnected: boolean;
  /** 마지막 수신 메시지 */
  lastMessage: WebSocketMessage<T> | null;
  /** 메시지 전송 함수 */
  sendMessage: (message: WebSocketMessage<T>) => void;
  /** 수동 연결 함수 */
  connect: () => void;
  /** 수동 연결 해제 함수 */
  disconnect: () => void;
  /** 재연결 시도 횟수 */
  reconnectCount: number;
}

/**
 * WebSocket 연결을 관리하는 React Hook
 * 
 * @param url - WebSocket 서버 URL
 * @param options - 옵션
 * @returns WebSocket 상태 및 제어 함수
 * 
 * @example
 * ```typescript
 * const { isConnected, lastMessage, sendMessage } = useWebSocket(
 *   getWebSocketUrl(),
 *   {
 *     onOpen: () => logger.log('Connected'),
 *     onClose: () => logger.log('Disconnected'),
 *   }
 * );
 * ```
 */
export function useWebSocket<T = unknown>(
  url: string,
  options: UseWebSocketOptions<T> = {}
): UseWebSocketReturn<T> {
  const {
    autoConnect = true,
    reconnect = true,
    onOpen,
    onClose,
    onError,
    onMessage,
  } = options;

  // 상태 관리
  const [status, setStatus] = useState<WebSocketStatus>(WebSocketStatus.DISCONNECTED);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage<T> | null>(null);
  const [reconnectCount, setReconnectCount] = useState(0);

  // Ref 관리
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeoutId = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectCountRef = useRef(0);
  const manuallyDisconnected = useRef(false);
  const isMounted = useRef(true);
  const socketIdRef = useRef(0);
  const connectRef = useRef<(() => void) | undefined>(undefined);
  const reconnectOptionRef = useRef(reconnect);

  // reconnect 옵션 최신값 유지
  useEffect(() => {
    reconnectOptionRef.current = reconnect;
  }, [reconnect]);

  // 콜백 안정화
  const stableOnOpen = useCallback(() => {
    onOpen?.();
  }, [onOpen]);

  const stableOnClose = useCallback(() => {
    onClose?.();
  }, [onClose]);

  const stableOnError = useCallback((error: Event) => {
    onError?.(error);
  }, [onError]);

  const stableOnMessage = useCallback((message: WebSocketMessage<T>) => {
    onMessage?.(message);
  }, [onMessage]);

  /**
   * WebSocket 연결 함수 (내부 구현)
   */
  const connectImpl = useCallback(() => {
    // 이미 연결되어 있거나 연결 중이면 무시
    if (ws.current?.readyState === WebSocket.OPEN || 
        ws.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    // 수동 연결 시 플래그 초기화
    manuallyDisconnected.current = false;
    
    // 연결 시작 시 재연결 카운트 초기화 (새로운 연결 시도 간주)
    reconnectCountRef.current = 0;
    setReconnectCount(0);

    // 이전 타임아웃 정리
    if (reconnectTimeoutId.current) {
      clearTimeout(reconnectTimeoutId.current);
      reconnectTimeoutId.current = null;
    }

    try {
      setStatus(WebSocketStatus.CONNECTING);
      logger.debug('[WebSocket] Connecting to:', url);
      
      // 새로운 소켓 ID 생성
      socketIdRef.current += 1;
      const currentSocketId = socketIdRef.current;
      
      ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        // 소켓 ID 확인 (URL 변경으로 인한 오래된 소켓 무시)
        if (currentSocketId !== socketIdRef.current || !isMounted.current) return;
        
        logger.info('[WebSocket] Connected');
        setStatus(WebSocketStatus.CONNECTED);
        reconnectCountRef.current = 0;
        setReconnectCount(0);
        stableOnOpen();
      };

      ws.current.onmessage = (event) => {
        if (currentSocketId !== socketIdRef.current || !isMounted.current) return;

        try {
          const message: WebSocketMessage<T> = JSON.parse(event.data);
          setLastMessage(message);
          stableOnMessage(message);
        } catch (error) {
          logger.error('[WebSocket] Failed to parse message:', error);
        }
      };

      ws.current.onclose = () => {
        if (currentSocketId !== socketIdRef.current || !isMounted.current) return;

        logger.info('[WebSocket] Disconnected');
        setStatus(WebSocketStatus.DISCONNECTED);
        stableOnClose();

        // 재연결 로직 - 최신 reconnect 옵션 사용
        if (!reconnectOptionRef.current || manuallyDisconnected.current || !isMounted.current) {
          return;
        }

        setStatus(WebSocketStatus.RECONNECTING);

        const attempt = reconnectCountRef.current;
        const delay = Math.min(
          WEBSOCKET_CONFIG.INITIAL_RECONNECT_DELAY * Math.pow(2, attempt),
          WEBSOCKET_CONFIG.MAX_RECONNECT_DELAY
        );

        const maxAttempts = WEBSOCKET_CONFIG.MAX_RECONNECT_ATTEMPTS;
        const shouldAttemptReconnect = maxAttempts === -1 || attempt < maxAttempts;

        if (!shouldAttemptReconnect) {
          logger.error('[WebSocket] Max reconnect attempts reached');
          setStatus(WebSocketStatus.ERROR);
          return;
        }

        logger.debug(`[WebSocket] Reconnecting in ${delay}ms (Attempt ${attempt + 1})`);
        reconnectTimeoutId.current = setTimeout(() => {
          if (!isMounted.current) return;
          
          reconnectCountRef.current += 1;
          setReconnectCount(reconnectCountRef.current);
          connectRef.current?.();
        }, delay);
      };

      ws.current.onerror = (error) => {
        if (currentSocketId !== socketIdRef.current || !isMounted.current) return;

        logger.error('[WebSocket] Connection error:', error);
        setStatus(WebSocketStatus.ERROR);
        stableOnError(error);
      };
    } catch (error) {
      logger.error('[WebSocket] Failed to create connection:', error);
      setStatus(WebSocketStatus.ERROR);
    }
  }, [url, stableOnOpen, stableOnClose, stableOnError, stableOnMessage]);

  // connectRef 업데이트
  useEffect(() => {
    connectRef.current = connectImpl;
  }, [connectImpl]);

  /**
   * WebSocket 연결 함수 (외부 노출)
   */
  const connect = useCallback(() => {
    connectRef.current?.();
  }, []);

  /**
   * WebSocket 연결 해제 함수
   */
  const disconnect = useCallback(() => {
    manuallyDisconnected.current = true;
    logger.debug('[WebSocket] Manual disconnect initiated');

    // 재연결 타임아웃 정리
    if (reconnectTimeoutId.current) {
      clearTimeout(reconnectTimeoutId.current);
      reconnectTimeoutId.current = null;
    }

    // WebSocket 연결 종료
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }

    setStatus(WebSocketStatus.DISCONNECTED);
    reconnectCountRef.current = 0;
    setReconnectCount(0);
  }, []);

  /**
   * 메시지 전송 함수
   */
  const sendMessage = useCallback((message: WebSocketMessage<T>) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      try {
        const data = JSON.stringify(message);
        ws.current.send(data);
      } catch (error) {
        logger.error('[WebSocket] Failed to send message:', error);
      }
    } else {
      logger.warn('[WebSocket] Cannot send message: not connected');
    }
  }, []);

  // 자동 연결 및 정리
  useEffect(() => {
    isMounted.current = true;
    manuallyDisconnected.current = false;

    if (autoConnect) {
      connect();
    }

    return () => {
      isMounted.current = false;
      logger.debug('[WebSocket] Unmounting hook, cleaning up');

      // 타임아웃 정리
      if (reconnectTimeoutId.current) {
        clearTimeout(reconnectTimeoutId.current);
        reconnectTimeoutId.current = null;
      }

      // WebSocket 정리
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    };
  }, [url, autoConnect, connect]);

  return {
    status,
    isConnected: status === WebSocketStatus.CONNECTED,
    lastMessage,
    sendMessage,
    connect,
    disconnect,
    reconnectCount,
  };
}

// web_ui/src/hooks/useWebSocket.ts

import { useCallback, useEffect, useRef, useState } from 'react';
import { WEBSOCKET_CONFIG } from '@/config/websocket';
import { WebSocketStatus } from '@/types/websocket';

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
export interface UseWebSocketOptions {
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
  onMessage?: (message: WebSocketMessage) => void;
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
  sendMessage: (message: WebSocketMessage) => void;
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
 *     onOpen: () => console.log('Connected'),
 *     onClose: () => console.log('Disconnected'),
 *   }
 * );
 * ```
 */
export function useWebSocket<T = unknown>(
  url: string,
  options: UseWebSocketOptions = {}
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
  const reconnectTimeoutId = useRef<NodeJS.Timeout | null>(null);
  const shouldReconnect = useRef(reconnect);
  const isMounted = useRef(true);
  const connectRef = useRef<(() => void) | undefined>(undefined);

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

  const stableOnMessage = useCallback((message: WebSocketMessage) => {
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

    // 이전 타임아웃 정리
    if (reconnectTimeoutId.current) {
      clearTimeout(reconnectTimeoutId.current);
      reconnectTimeoutId.current = null;
    }

    try {
      setStatus(WebSocketStatus.CONNECTING);
      ws.current = new WebSocket(url);

      ws.current.onopen = () => {
        if (!isMounted.current) return;
        
        setStatus(WebSocketStatus.CONNECTED);
        setReconnectCount(0);
        stableOnOpen();
      };

      ws.current.onmessage = (event) => {
        if (!isMounted.current) return;

        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(message as WebSocketMessage<T>);
          stableOnMessage(message);
        } catch (error) {
          console.error('[WebSocket] Failed to parse message:', error);
        }
      };

      ws.current.onclose = () => {
        if (!isMounted.current) return;

        setStatus(WebSocketStatus.DISCONNECTED);
        stableOnClose();

        // 재연결 로직
        if (shouldReconnect.current && isMounted.current) {
          setStatus(WebSocketStatus.RECONNECTING);
          
          const delay = Math.min(
            WEBSOCKET_CONFIG.INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectCount),
            WEBSOCKET_CONFIG.MAX_RECONNECT_DELAY
          );

          const maxAttempts = WEBSOCKET_CONFIG.MAX_RECONNECT_ATTEMPTS;
          const shouldAttemptReconnect = maxAttempts === -1 || reconnectCount < maxAttempts;

          if (shouldAttemptReconnect) {
            reconnectTimeoutId.current = setTimeout(() => {
              if (isMounted.current) {
                setReconnectCount(prev => prev + 1);
                // connectRef를 통해 재귀 호출
                connectRef.current?.();
              }
            }, delay);
          } else {
            setStatus(WebSocketStatus.ERROR);
          }
        }
      };

      ws.current.onerror = (error) => {
        if (!isMounted.current) return;

        console.error('[WebSocket] Connection error:', error);
        setStatus(WebSocketStatus.ERROR);
        stableOnError(error);
      };
    } catch (error) {
      console.error('[WebSocket] Failed to create connection:', error);
      setStatus(WebSocketStatus.ERROR);
    }
  }, [url, reconnectCount, stableOnOpen, stableOnClose, stableOnError, stableOnMessage]);

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
    shouldReconnect.current = false;

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
    setReconnectCount(0);
  }, []);

  /**
   * 메시지 전송 함수
   */
  const sendMessage = useCallback((message: WebSocketMessage) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      try {
        const data = JSON.stringify(message);
        ws.current.send(data);
      } catch (error) {
        console.error('[WebSocket] Failed to send message:', error);
      }
    } else {
      console.warn('[WebSocket] Cannot send message: not connected');
    }
  }, []);

  // 자동 연결 및 정리
  useEffect(() => {
    isMounted.current = true;
    shouldReconnect.current = reconnect;

    if (autoConnect) {
      connect();
    }

    return () => {
      isMounted.current = false;
      shouldReconnect.current = false;

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
  }, [url, autoConnect, reconnect, connect]);

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

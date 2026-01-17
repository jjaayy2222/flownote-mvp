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
 * 보안을 위해 URL에서 쿼리 파라미터, 해시(Fragment) 등 민감 정보를 제거합니다.
 */
const sanitizeUrl = (url: string): string => {
  if (url.trim().length === 0) {
    return '[Invalid URL]';
  }
  const trimmed = url.trim();
  try {
    const parsed = new URL(trimmed);
    return `${parsed.protocol}//${parsed.host}${parsed.pathname}`;
  } catch {
    return trimmed.replace(/[?#].*$/, '');
  }
};

/**
 * binary 데이터를 수신했을 때(gzip 압축 등)의 처리 로직
 * 
 * @param data - 수신된 binary 데이터 (Blob 또는 ArrayBuffer)
 * @returns 압축 해제된 텍스트 데이터
 */
async function decompressMessage(data: Blob | ArrayBuffer): Promise<string> {
  if (typeof globalThis.DecompressionStream === 'undefined') {
    // Native API 미지원 시 (예: 매우 오래된 브라우저)
    // 현재 MVP 환경에서는 모던 브라우저를 타겟으로 하므로 에러 발생 또는 라이브러리 폴백 필요
    throw new Error('DecompressionStream is not supported in this browser');
  }

  try {
    const blob = data instanceof Blob ? data : new Blob([data]);
    const ds = new DecompressionStream('gzip');
    const decompressedStream = blob.stream().pipeThrough(ds);
    const response = new Response(decompressedStream);
    return await response.text();
  } catch (error) {
    throw new Error(`Failed to decompress message: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/**
 * WebSocket 연결을 관리하는 React Hook
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

    manuallyDisconnected.current = false;
    reconnectCountRef.current = 0;
    setReconnectCount(0);

    if (reconnectTimeoutId.current) {
      clearTimeout(reconnectTimeoutId.current);
      reconnectTimeoutId.current = null;
    }

    socketIdRef.current += 1;
    const currentSocketId = socketIdRef.current;

    try {
      setStatus(WebSocketStatus.CONNECTING);
      logger.debug(`[WebSocket:${currentSocketId}] Connecting to:`, sanitizeUrl(url));
      
      ws.current = new WebSocket(url);
      
      // Binary 데이터 처리를 위해 blob 타입 사용 (DecompressionStream 연동)
      ws.current.binaryType = 'blob';

      ws.current.onopen = () => {
        if (currentSocketId !== socketIdRef.current || !isMounted.current) return;
        
        logger.info(`[WebSocket:${currentSocketId}] Connected`);
        setStatus(WebSocketStatus.CONNECTED);
        reconnectCountRef.current = 0;
        setReconnectCount(0);
        stableOnOpen();
      };

      ws.current.onmessage = async (event) => {
        if (currentSocketId !== socketIdRef.current || !isMounted.current) return;

        try {
          let rawData: string;
          
          if (typeof event.data === 'string') {
            rawData = event.data;
          } else {
            // Binary 데이터 (Blob) 수신 시 압축 해제 시도
            logger.debug(`[WebSocket:${currentSocketId}] Binary message received (${event.data.size} bytes), decompressing...`);
            rawData = await decompressMessage(event.data);
          }

          const message: WebSocketMessage<T> = JSON.parse(rawData);
          setLastMessage(message);
          stableOnMessage(message);
        } catch (error) {
          logger.error(`[WebSocket:${currentSocketId}] Failed to process message:`, error);
        }
      };

      ws.current.onclose = () => {
        if (currentSocketId !== socketIdRef.current || !isMounted.current) return;

        logger.info(`[WebSocket:${currentSocketId}] Disconnected`);
        setStatus(WebSocketStatus.DISCONNECTED);
        stableOnClose();

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
          logger.error(`[WebSocket:${currentSocketId}] Max reconnect attempts reached`);
          setStatus(WebSocketStatus.ERROR);
          return;
        }

        logger.debug(`[WebSocket:${currentSocketId}] Reconnecting in ${delay}ms (Attempt ${attempt + 1})`);
        reconnectTimeoutId.current = setTimeout(() => {
          if (!isMounted.current) return;
          
          reconnectCountRef.current += 1;
          setReconnectCount(reconnectCountRef.current);
          connectRef.current?.();
        }, delay);
      };

      ws.current.onerror = (error) => {
        if (currentSocketId !== socketIdRef.current || !isMounted.current) return;

        logger.error(`[WebSocket:${currentSocketId}] Connection error:`, error);
        setStatus(WebSocketStatus.ERROR);
        stableOnError(error);
      };
    } catch (error) {
      logger.error(`[WebSocket:${currentSocketId}] Failed to create connection:`, error);
      setStatus(WebSocketStatus.ERROR);
    }
  }, [url, stableOnOpen, stableOnClose, stableOnError, stableOnMessage]);

  // connectRef 업데이트
  useEffect(() => {
    connectRef.current = connectImpl;
  }, [connectImpl]);

  const connect = useCallback(() => {
    connectRef.current?.();
  }, []);

  const disconnect = useCallback(() => {
    manuallyDisconnected.current = true;
    const currentSocketId = socketIdRef.current;
    
    logger.debug(`[WebSocket:${currentSocketId}] Manual disconnect initiated`);

    if (reconnectTimeoutId.current) {
      clearTimeout(reconnectTimeoutId.current);
      reconnectTimeoutId.current = null;
    }

    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }

    setStatus(WebSocketStatus.DISCONNECTED);
    reconnectCountRef.current = 0;
    setReconnectCount(0);
  }, []);

  const sendMessage = useCallback((message: WebSocketMessage<T>) => {
    const currentSocketId = socketIdRef.current;
    
    if (ws.current?.readyState === WebSocket.OPEN) {
      try {
        const data = JSON.stringify(message);
        ws.current.send(data);
      } catch (error) {
        logger.error(`[WebSocket:${currentSocketId}] Failed to send message:`, error);
      }
    } else {
      logger.warn(`[WebSocket:${currentSocketId}] Cannot send message: not connected`);
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
      const currentSocketId = socketIdRef.current;
      logger.debug(`[WebSocket:${currentSocketId}] Unmounting hook, cleaning up`);

      if (reconnectTimeoutId.current) {
        clearTimeout(reconnectTimeoutId.current);
        reconnectTimeoutId.current = null;
      }

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

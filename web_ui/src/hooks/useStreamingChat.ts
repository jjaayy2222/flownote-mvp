// web_ui/src/hooks/useStreamingChat.ts

import { useState, useCallback, useRef } from 'react';
import {
  fetchChatStream,
  type StreamChatRequest,
  type StreamChunkError,
} from '@/lib/stream-client';
import type { SourceItem } from '@/types/chat';

// =============================================================================
// 타입 정의
// =============================================================================

/** 스트리밍 에러 상태 타입 (내부 코드 노출 없이 사용자 친화적 정보만 포함) */
export interface StreamError {
  /** 에러 분류 코드 (내부 로직용, 사용자에게 직접 표시 금지) */
  errorCode: string;
  /** 사용자에게 표시할 메시지 */
  message: string;
}

/** useStreamingChat 훅의 반환 타입 */
export interface UseStreamingChatReturn {
  /** 지금까지 수신된 누적 토큰 문자열 (부분 마크다운 포함 가능) */
  tokens: string;
  /** 스트리밍이 진행 중인지 여부 */
  isStreaming: boolean;
  /** 수신된 소스 문서 목록 */
  sources: SourceItem[];
  /** 에러 상태 (없으면 null) */
  error: StreamError | null;
  /** 스트리밍을 시작합니다. 이미 진행 중인 경우 기존 스트림을 먼저 중단합니다. */
  startStream: (payload: StreamChatRequest) => void;
  /** 진행 중인 스트림을 취소합니다. */
  cancelStream: () => void;
}

// =============================================================================
// 커스텀 훅
// =============================================================================

/**
 * SSE 기반 실시간 스트리밍 채팅을 위한 React 커스텀 훅.
 *
 * - AbortController를 통한 취소 및 클린업 보장
 * - 상태 관리: tokens(누적 토큰), isStreaming, sources, error
 * - useEffect 클린업 없이도 cancelStream() 호출로 명시적 중단 가능
 *
 * @example
 * ```tsx
 * const { tokens, isStreaming, error, startStream, cancelStream } = useStreamingChat();
 *
 * // 스트림 시작
 * startStream({ query: '안녕하세요', user_id: userId, session_id: sessionId });
 *
 * // 스트림 취소
 * cancelStream();
 * ```
 */
export function useStreamingChat(): UseStreamingChatReturn {
  const [tokens, setTokens] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [error, setError] = useState<StreamError | null>(null);

  // 진행 중인 스트림의 AbortController를 ref로 관리하여
  // 상태 업데이트를 트리거하지 않고 안전하게 접근 가능
  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * 진행 중인 스트림을 안전하게 중단합니다.
   * 이미 완료되었거나 없는 경우 무시합니다.
   */
  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  /**
   * 스트리밍을 시작합니다.
   * 이미 진행 중인 스트림이 있으면 먼저 취소한 후 새 스트림을 시작합니다.
   */
  const startStream = useCallback(
    (payload: StreamChatRequest) => {
      // 진행 중인 스트림이 있으면 먼저 취소
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      // 새 컨트롤러 생성 및 상태 초기화
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setTokens('');
      setSources([]);
      setError(null);
      setIsStreaming(true);

      // 비동기 스트림 소비 (async IIFE)
      (async () => {
        try {
          for await (const chunk of fetchChatStream(payload, controller.signal)) {
            // 컨트롤러가 교체된 경우(다른 startStream 호출) 이 스트림 결과는 무시
            if (abortControllerRef.current !== controller) return;

            switch (chunk.type) {
              case 'token':
                setTokens((prev) => prev + chunk.data);
                break;
              case 'sources':
                setSources(chunk.data);
                break;
              case 'error': {
                // [보안] 내부 에러 코드는 상태에만 저장하고 직접 렌더링하지 않음
                const errChunk = chunk as StreamChunkError;
                setError({
                  errorCode: errChunk.error_code,
                  message: errChunk.message,
                });
                break;
              }
              case 'done':
                // 정상 완료 - 별도 처리 불필요
                break;
            }
          }
        } catch (err: unknown) {
          // 이 스트림이 이미 교체된 경우 에러 무시
          if (abortControllerRef.current !== controller) return;

          // AbortError는 사용자가 직접 cancelStream()을 호출한 정상 흐름
          const isAbort =
            (err instanceof Error && err.name === 'AbortError') ||
            (typeof DOMException !== 'undefined' &&
              err instanceof DOMException &&
              err.name === 'AbortError');

          if (!isAbort) {
            console.error('[useStreamingChat] Unexpected stream error:', err);
            setError({
              errorCode: 'STREAM_ERROR',
              message: err instanceof Error ? err.message : '스트리밍 중 오류가 발생했습니다.',
            });
          }
        } finally {
          // 이 스트림이 여전히 현재 스트림인 경우에만 상태 클린업
          if (abortControllerRef.current === controller) {
            abortControllerRef.current = null;
            setIsStreaming(false);
          }
        }
      })();
    },
    [] // 의존성 없음: AbortController는 ref로 관리되므로 안정적
  );

  return {
    tokens,
    isStreaming,
    sources,
    error,
    startStream,
    cancelStream,
  };
}

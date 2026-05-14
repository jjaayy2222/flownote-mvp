// web_ui/src/hooks/useStreamingChat.ts

import { useState, useCallback, useRef, useEffect } from 'react';
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

/** useStreamingChat 훅의 옵션 타입 */
export interface UseStreamingChatOptions {
  /**
   * 예상치 못한 스트림 에러 발생 시 호출되는 콜백.
   * 기본값: console.error (개발 환경용)
   * 운영 환경에서는 Sentry 등 외부 모니터링 유틸리티로 교체 권장.
   * [보안] StreamError 타입을 통해 내부 에러 코드와 사용자 메시지가 분리되어 전달됩니다.
   */
  onError?: (error: StreamError, raw: unknown) => void;
  /**
   * 스트림이 성공적으로 완료되었을 때 호출되는 콜백.
   * 스트리밍된 결과물을 메인 대화 이력 등에 영구 저장할 때 유용합니다.
   */
  onFinish?: (content: string, sources: SourceItem[]) => void;
}

// =============================================================================
// 커스텀 훅
// =============================================================================

/**
 * SSE 기반 실시간 스트리밍 채팅을 위한 React 커스텀 훅.
 *
 * - AbortController를 통한 취소 및 클린업 보장
 * - useEffect 클린업으로 언마운트 시 자동 스트림 중단 보장
 * - 상태 관리: tokens(누적 토큰), isStreaming, sources, error
 * - onError 콜백을 주입하여 에러 리포팅 전략을 외부에서 제어 가능
 *
 * @example
 * ```tsx
 * const { tokens, isStreaming, error, startStream, cancelStream } = useStreamingChat({
 *   onError: (err, raw) => Sentry.captureException(raw),
 * });
 *
 * // 스트림 시작
 * startStream({ query: '안녕하세요', user_id: userId, session_id: sessionId });
 *
 * // 스트림 취소
 * cancelStream();
 * ```
 */
export function useStreamingChat(options: UseStreamingChatOptions = {}): UseStreamingChatReturn {
  const [tokens, setTokens] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [error, setError] = useState<StreamError | null>(null);

  // 진행 중인 스트림의 AbortController를 ref로 관리하여
  // 상태 업데이트를 트리거하지 않고 안전하게 접근 가능
  const abortControllerRef = useRef<AbortController | null>(null);

  // 콜백들을 ref로 보관하여 콜백이 바뀌어도 startStream 재생성을 방지
  const onErrorRef = useRef(options.onError);
  const onFinishRef = useRef(options.onFinish);
  useEffect(() => {
    onErrorRef.current = options.onError;
    onFinishRef.current = options.onFinish;
  }, [options.onError, options.onFinish]);

  // [언마운트 클린업] 컴포넌트 해제 시 진행 중인 스트림을 자동으로 중단하여
  // 언마운트된 컴포넌트에서 setState가 호출되는 것을 방지합니다.
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
    };
  }, []);

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
        let accumulatedTokens = '';
        let finalSources: SourceItem[] = [];

        try {
          for await (const chunk of fetchChatStream(payload, controller.signal)) {
            // 컨트롤러가 교체된 경우(다른 startStream 호출) 이 스트림 결과는 무시
            if (abortControllerRef.current !== controller) return;

            switch (chunk.type) {
              case 'token':
                accumulatedTokens += chunk.data;
                setTokens(accumulatedTokens);
                break;
              case 'sources':
                finalSources = chunk.data;
                setSources(finalSources);
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
                // 정상 완료 - 누적된 토큰과 소스를 부모에게 전달
                onFinishRef.current?.(accumulatedTokens, finalSources);
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
            const streamErr: StreamError = {
              errorCode: 'STREAM_ERROR',
              message: err instanceof Error ? err.message : '스트리밍 중 오류가 발생했습니다.',
            };
            // [보안/방어] onError 콜백을 통해 에러 리포팅을 외부에서 제어.
            // 사용자 제공 콜백이 예외를 던지더라도 setError는 반드시 실행되어야 하므로
            // try/catch로 격리하고, 콜백 실패 시 console.error로 폴백합니다.
            try {
              const reporter = onErrorRef.current ?? console.error;
              reporter(streamErr, err);
            } catch (reporterErr: unknown) {
              console.error('[useStreamingChat] onError callback threw an exception:', reporterErr);
            }
            setError(streamErr);
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

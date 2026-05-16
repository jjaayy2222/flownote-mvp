'use client';

import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { useChat } from '@ai-sdk/react';
import type { UIMessage } from 'ai';
import { DefaultChatTransport } from 'ai';
import { CHAT_CONFIG, STORAGE_KEYS, UI_CONFIG, FEATURE_FLAGS } from '@/lib/constants';
import { useStreamingChat } from '@/hooks/useStreamingChat';
import type { StreamChatRequest } from '@/lib/stream-client';
import { MessageBubble } from './MessageBubble';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Send, Loader2, ChevronDown } from 'lucide-react';
import { toast } from 'sonner';

/**
 * 공용 에러 배너 컴포넌트
 */
function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      className="p-4 mb-4 bg-red-50 border border-red-100 rounded-xl text-xs text-red-600 flex items-center gap-2 animate-in fade-in slide-in-from-top-2"
    >
      <span className="font-bold">Error:</span>
      <span>{message}</span>
      {onRetry && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onRetry}
          className="ml-auto h-6 text-[10px] hover:bg-red-100"
        >
          재시도
        </Button>
      )}
    </div>
  );
}

const TYPING_ANIMATION_DELAYS = ['[animation-delay:-0.3s]', '[animation-delay:-0.15s]', ''];

/**
 * 스트리밍 대기 시 보여지는 타이핑 인디케이터
 */
function TypingIndicator({ className = '' }: { className?: string }) {
  return (
    <div className={`flex justify-start px-1 py-2 ${className}`}>
      <div 
        className="max-w-[80%] rounded-2xl rounded-tl-sm bg-slate-50 border border-slate-100 px-4 py-4 flex items-center gap-1.5"
        role="status"
        aria-live="polite"
      >
        {TYPING_ANIMATION_DELAYS.map((delayClass, index) => (
          <div 
            key={index}
            className={`w-2 h-2 bg-slate-400 rounded-full animate-bounce ${delayClass}`} 
            aria-hidden="true" 
          />
        ))}
        <span className="sr-only">응답 작성 중...</span>
      </div>
    </div>
  );
}

/** 초기 환영 메시지 */
const WELCOME_MESSAGE: UIMessage = {
  id: 'welcome',
  role: 'assistant',
  parts: [
    {
      type: 'text',
      text: '안녕하세요! 저는 **Flownote AI 어시스턴트**입니다.\n지금까지 작성하신 메모와 노트를 바탕으로 사용자님의 직업, 목표, 통찰력 등을 파악하여 대답할 수 있습니다. 어떻게 도와드릴까요?',
    },
  ],
};

const defaultChatTransport = new DefaultChatTransport({ api: '/api/chat' });

interface HistoryMessage {
  role: 'assistant' | 'user';
  content: string;
  timestamp?: string | number;
}

/**
 * 범용 ID 생성 헬퍼
 */
function generateId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

/**
 * Storage에서 ID를 가져오거나 없으면 새로 생성하여 저장하는 유틸리티
 */
function getOrCreateStoredId(storageKey: string, prefix: string): string {
  if (typeof window === 'undefined') return '';

  let id: string | null = null;
  try {
    id = localStorage.getItem(storageKey);
  } catch (err) {
    console.warn(`[Storage] Failed to read ${storageKey}:`, err);
  }

  if (!id) {
    id = generateId(prefix);
    try {
      localStorage.setItem(storageKey, id);
    } catch (err) {
      console.warn(`[Storage] Failed to save ${storageKey}:`, err);
    }
  }
  return id;
}

interface ChatWindowProps {
  externalSessionId?: string;
  externalUserId?: string;
  onSessionChange?: (sessionId: string) => void;
  headerLeftSlot?: React.ReactNode;
}

export function ChatWindow({ 
  externalSessionId, 
  externalUserId,
  onSessionChange,
  headerLeftSlot
}: ChatWindowProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);

  const [input, setInput] = useState('');
  const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [hasUnreadMessages, setHasUnreadMessages] = useState(false);

  // 계층화된 세션 상태 관리 (Prop 우선 -> Storage)
  const [sessionId, setSessionId] = useState<string>(() => 
    externalSessionId || getOrCreateStoredId(STORAGE_KEYS.CHAT_SESSION_ID, 'sess')
  );

  const [userId] = useState<string>(() => 
    externalUserId || getOrCreateStoredId(STORAGE_KEYS.USER_ID, 'user')
  );

  // Prop 변화 감지하여 상태 동기화
  useEffect(() => {
    if (externalSessionId && externalSessionId !== sessionId) {
      setSessionId(externalSessionId);
    }
  }, [externalSessionId, sessionId]);

  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [alpha, setAlpha] = useState<number>(CHAT_CONFIG.DEFAULT_ALPHA);

  const getOrInitViewport = useCallback((): HTMLDivElement | null => {
    const container = scrollContainerRef.current;
    if (!container) return null;

    if (viewportRef.current && 
        viewportRef.current.isConnected && 
        container.contains(viewportRef.current)) {
      return viewportRef.current;
    }

    const el = container.querySelector('[data-radix-scroll-area-viewport]');
    const viewport = el instanceof HTMLDivElement ? el : null;
    viewportRef.current = viewport;
    return viewport;
  }, []);

  const scrollToBottom = useCallback((behavior: 'auto' | 'smooth' = 'auto') => {
    const viewport = getOrInitViewport();
    if (viewport && (autoScrollEnabled || behavior === 'smooth')) {
      viewport.scrollTo({
        top: viewport.scrollHeight,
        behavior: behavior
      });
      
      if (behavior === 'smooth') {
        setAutoScrollEnabled(true);
        setShowScrollButton(false);
        setHasUnreadMessages(false);
      }
    }
  }, [autoScrollEnabled, getOrInitViewport]);

  const handleScrollManual = useCallback(() => {
    const viewport = getOrInitViewport();
    if (!viewport) return;

    const { scrollTop, scrollHeight, clientHeight } = viewport;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    
    // [Refinement] UI_CONFIG.SCROLL_THRESHOLD 직접 사용 (중복 제거)
    const isNowAtBottom = distanceFromBottom < UI_CONFIG.SCROLL_THRESHOLD;
    
    if (isNowAtBottom) {
      if (!autoScrollEnabled) setAutoScrollEnabled(true);
      if (showScrollButton) setShowScrollButton(false);
      if (hasUnreadMessages) setHasUnreadMessages(false);
    } else {
      if (autoScrollEnabled) setAutoScrollEnabled(false);
      if (!showScrollButton) setShowScrollButton(true);
    }
  }, [autoScrollEnabled, showScrollButton, hasUnreadMessages, getOrInitViewport]);

  const handleUserInteraction = useCallback(() => {
    if (autoScrollEnabled) {
      setAutoScrollEnabled(false);
      setShowScrollButton(true);
    }
  }, [autoScrollEnabled]);

  const chatOptions = useMemo(() => ({
    messages: [WELCOME_MESSAGE],
    transport: defaultChatTransport,
    body: {
      user_id: userId || CHAT_CONFIG.DEFAULT_USER_ID,
      session_id: sessionId,
      alpha: alpha,
      k: CHAT_CONFIG.DEFAULT_K,
    },
    onError: (err: Error) => {
      toast.error('메시지 전송 중 에러가 발생했습니다.', {
        description: err.message || '서버와의 연결을 확인해주세요.',
      });
      console.error('[ChatWindow] useChat Error:', err);
    },
    onFinish: () => {
      scrollToBottom();
    },
  }), [userId, sessionId, alpha, scrollToBottom]);

  const { messages, sendMessage, status, setMessages, error } = useChat(chatOptions);

  // =========================================================================
  // [스트리밍 훅] 플래그 활성화 시 useStreamingChat 사용
  // 기존 useChat 방식과 공존하며, 플래그 토글로 즉시 전환 가능합니다.
  // =========================================================================

  // [DRY] 플래그를 한 번만 참조하여 컴포넌트 전체에서 사용
  const isStreamingMode = FEATURE_FLAGS.USE_STREAMING;

  const {
    tokens: streamTokens,
    isStreaming,
    // sources는 향후 SourcePanel 컴포넌트 연결 시 추가 예정
    error: streamError,
    startStream,
    cancelStream,
  } = useStreamingChat({
    onError: (err, raw) => {
      // [보안] 운영 환경에서는 원본 raw 에러 객체를 콘솔에 노출하지 않습니다.
      // 내부 스택 트레이스나 서버 세부정보 노출 위험이 있으므로, 개발 환경에서만 로깅합니다.
      if (process.env.NODE_ENV !== 'production') {
        console.error('[ChatWindow] Stream error (dev only):', raw);
      }
      toast.error('스트리밍 중 오류가 발생했습니다.', {
        description: err.message,
      });
    },
    onFinish: (content) => {
      // 스트리밍이 끝나면 영구적인 messages 배열에 추가하여 
      // 리렌더링이나 히스토리에서 일관되게 보이도록 합니다.
      if (!content) return;
      setMessages((prev) => [
        ...prev,
        {
          id: generateId('ast'),
          role: 'assistant',
          parts: [{ type: 'text', text: content }],
        },
      ]);
    },
  });

  useEffect(() => {
    if (!sessionId) return;
    let ignore = false;
    setMessages([WELCOME_MESSAGE]);

    const loadHistory = async () => {
      setIsHistoryLoading(true);
      try {
        const res = await fetch(`/api/chat/history?session_id=${sessionId}`);
        if (ignore) return;

        if (res.ok) {
          // [Refinement] Content-Type 체크 및 JSON 파싱 에러 가시화
          const contentType = res.headers.get('content-type');
          if (!contentType || !contentType.includes('application/json')) {
            throw new Error(`Unexpected content-type: ${contentType}`);
          }

          const data = await res.json().catch((err) => {
            console.error('[ChatWindow] JSON Parsing Error:', err);
            return { messages: [] };
          });

          if (data.messages && data.messages.length > 0) {
            const historyMessages: UIMessage[] = data.messages.map((m: HistoryMessage, index: number) => ({
              id: `hist-${index}-${sessionId}`,
              role: m.role,
              parts: [{ type: 'text', text: m.content }],
              createdAt: m.timestamp ? new Date(m.timestamp) : undefined,
            }));

            setMessages(prev => {
              const currentMessages = prev.filter(m => m.id !== 'welcome');
              return [WELCOME_MESSAGE, ...historyMessages, ...currentMessages];
            });
          }
        } else {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.error || 'Failed to load history');
        }
      } catch (err: unknown) {
        if (!ignore) {
          const errMsg = err instanceof Error ? err.message : 'Unknown error';
          console.error('[ChatWindow] History Load Error:', err);
          toast.error('대화 내역 로드 실패', { description: errMsg });
        }
      } finally {
        if (!ignore) setIsHistoryLoading(false);
      }
    };

    loadHistory();
    return () => { ignore = true; };
  }, [sessionId, setMessages]);

  const handleClearHistory = async () => {
    if (!sessionId || !confirm('대화 내용을 모두 초기화하시겠습니까?')) return;
    try {
      const res = await fetch(`/api/chat/history?session_id=${sessionId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to clear history');

      const newSid = generateId('sess');
      
      // [Review 반영] 저장소 쓰기 성공 시에만 메모리 상태 업데이트
      localStorage.setItem(STORAGE_KEYS.CHAT_SESSION_ID, newSid);
      
      setSessionId(newSid);
      onSessionChange?.(newSid);
      setMessages([WELCOME_MESSAGE]);
      toast.success('대화가 초기화되었습니다.');
    } catch (err: unknown) {
      console.error('[ChatWindow] Clear/Reset History Error:', err);
      toast.error('초기화 중 오류 발생', {
        description: err instanceof Error ? err.message : '저장소 권한을 확인해주세요.'
      });
    }
  };

  // 플래그에 따라 로딩 상태를 통합 (기존 useChat 방식 또는 스트리밍 방식)
  const isLoading = isStreamingMode
    ? isStreaming
    : status === 'streaming' || status === 'submitted';

  useEffect(() => {
    if (autoScrollEnabled) {
      scrollToBottom();
    } else if (isLoading) {
      setHasUnreadMessages(true);
    }
  }, [messages, isLoading, autoScrollEnabled, scrollToBottom]);

  const handleSubmit = useCallback((e?: React.FormEvent) => {
    e?.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    if (isStreamingMode) {
      // 스트리밍 훅 방식: useStreamingChat.startStream() 호출
      const payload: StreamChatRequest = {
        query: trimmed,
        user_id: userId || CHAT_CONFIG.DEFAULT_USER_ID || '',
        session_id: sessionId,
        k: CHAT_CONFIG.DEFAULT_K,
        alpha: alpha,
      };
      startStream(payload);
    } else {
      // 폴백: 기존 useChat 방식
      sendMessage({ role: 'user', parts: [{ type: 'text', text: trimmed }] });
    }

    setInput('');
  }, [input, isLoading, isStreamingMode, sendMessage, startStream, userId, sessionId, alpha]);

  const handleRetry = useCallback(() => {
    if (isLoading) return;
    
    // 마지막 사용자 메시지를 찾아 다시 전송 시도
    const lastUserMessage = [...messages].reverse().find(m => m.role === 'user');
    const content = lastUserMessage?.parts?.[0]?.type === 'text' ? lastUserMessage.parts[0].text : '';
    
    if (content) {
      sendMessage({ role: 'user', parts: [{ type: 'text', text: content }] });
    } else {
      // 메시지를 찾을 수 없는 경우 기존 handleSubmit 호출 (input에 텍스트가 남았을 때 대비)
      handleSubmit();
    }
  }, [messages, isLoading, sendMessage, handleSubmit]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div 
      className="flex flex-col w-full border-none shadow-none bg-transparent overflow-hidden relative h-full"
    >
      <div className="bg-white/80 backdrop-blur-md border-b px-4 md:px-6 py-3 md:py-4 flex items-center justify-between shadow-sm z-10 sticky top-0">
        <div className="flex items-center gap-2 md:gap-4">
          {headerLeftSlot}
          <div>
            <h2 className="text-base md:text-lg font-bold text-slate-800 tracking-tight leading-tight">Flownote AI</h2>
            <p className="text-[10px] md:text-xs text-slate-500 font-medium hidden sm:block">사용자 데이터 기반 RAG 에이전트</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden md:flex flex-col items-end mr-2">
            <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Alpha (Dense/FAISS)</span>
            <select 
              value={alpha} 
              aria-label="Alpha weighting for hybrid search"
              onChange={(e) => setAlpha(parseFloat(e.target.value))}
              className="text-xs bg-transparent border-none focus:ring-0 text-slate-600 font-medium cursor-pointer"
            >
              <option value="0.0">0.0 (Keyword) </option>
              <option value="0.3">0.3 </option>
              <option value="0.5">0.5 </option>
              <option value="0.7">0.7 </option>
              <option value="1.0">1.0 (Semantic) </option>
            </select>
          </div>

          <Button variant="ghost" size="sm" onClick={handleClearHistory} className="text-slate-400 hover:text-red-500 hover:bg-red-50 text-xs h-8">
            초기화
          </Button>

          {(isLoading || isHistoryLoading) && (
            <div className="flex items-center gap-1.5 text-xs text-blue-500 bg-blue-50 px-2.5 py-1 rounded-full border border-blue-100">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>{isHistoryLoading ? '로드 중...' : '생성 중...'}</span>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-hidden relative group">
        <ScrollArea 
          className="h-full w-full" 
          ref={scrollContainerRef}
          onScrollCapture={handleScrollManual}
          onWheel={handleUserInteraction}
          onTouchStart={handleUserInteraction}
        >
          <div className="flex flex-col gap-0 w-full max-w-4xl mx-auto p-4 py-8">
            {messages.map((m: UIMessage, idx: number) => (
              <MessageBubble 
                key={m.id} 
                message={m} 
                isLast={idx === messages.length - 1} 
                isStreaming={status === 'streaming'}
                sessionId={sessionId}
              />
            ))}
            {/* [스트리밍 모드] 첫 토큰 도착 전 타이핑 인디케이터 */}
            {isStreamingMode && isStreaming && (streamTokens == null || streamTokens === '') && (
              <TypingIndicator />
            )}

            {/* [스트리밍 모드] 누적 토큰을 실시간으로 렌더링 */}
            {isStreamingMode && streamTokens && (
              <div className="flex justify-start px-1 py-2">
                <div className="max-w-[80%] rounded-2xl rounded-tl-sm bg-slate-50 border border-slate-100 px-4 py-3 text-sm text-slate-800 whitespace-pre-wrap">
                  {streamTokens}
                  {isStreaming && (
                    <span className="inline-block w-1.5 h-4 bg-slate-400 rounded-sm ml-0.5 animate-pulse" aria-hidden="true" />
                  )}
                </div>
              </div>
            )}

            {/* 에러 UI: 스크린 리더가 DOM 삽입을 항상 감지할 수 있도록 라이브 리전 컨테이너를 상시 렌더링합니다. */}
            <div aria-live="assertive" aria-atomic="true">
              {isStreamingMode ? (
                streamError && <ErrorBanner message={streamError.message} />
              ) : (
                error && (
                  <ErrorBanner
                    message={error.message || '메시지 전송 중 오류가 발생했습니다.'}
                    onRetry={handleRetry}
                  />
                )
              )}
            </div>
            <div className="h-4" />
          </div>
        </ScrollArea>

        {showScrollButton && (
          <Button
            size="sm"
            onClick={() => scrollToBottom('smooth')}
            aria-label="최근 메시지로 이동"
            className={`
              absolute bottom-6 right-8 rounded-full shadow-lg border border-slate-200 
              bg-white/90 backdrop-blur-sm hover:bg-slate-50 text-slate-600 z-20 
              flex items-center gap-2 px-4 h-10 transition-all 
              animate-in fade-in zoom-in duration-300
              ${hasUnreadMessages ? 'ring-2 ring-blue-500 ring-offset-2' : ''}
            `}
          >
            <ChevronDown className={`w-4 h-4 ${hasUnreadMessages ? 'text-blue-500 animate-bounce' : 'text-slate-400'}`} />
            <span className="text-xs font-bold text-slate-700">
              {hasUnreadMessages ? '새 메시지 도착' : '최근 메시지로 이동'}
            </span>
          </Button>
        )}
      </div>

      <div className="p-4 bg-white/80 backdrop-blur-md border-t border-slate-200 sticky bottom-0 z-10 w-full">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto flex gap-4 items-end">
          <div className="relative w-full shadow-sm rounded-xl">
            <Textarea
              id="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="메시지를 입력하세요..."
              className="w-full resize-none pr-12 bg-white rounded-xl border-slate-200 focus-visible:ring-1 focus-visible:ring-slate-400 min-h-[56px] max-h-40 text-base py-4"
              rows={1}
              disabled={isLoading}
            />
            <Button
              type="submit"
              size="icon"
              aria-label="메시지 전송"
              disabled={!input.trim() || isLoading}
              className="absolute right-3 bottom-3 h-8 w-8 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white transition-opacity disabled:opacity-50"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4 ml-0.5" />}
            </Button>

            {/* [스트리밍 모드] 진행 중 취소 버튼 */}
            {isStreamingMode && isStreaming && (
              <Button
                type="button"
                size="sm"
                aria-label="스트리밍 취소"
                onClick={cancelStream}
                className="absolute right-14 bottom-3 h-8 px-3 rounded-lg bg-red-50 hover:bg-red-100 text-red-500 text-xs font-medium"
              >
                중단
              </Button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

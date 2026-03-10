'use client';

import React, { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { useChat } from '@ai-sdk/react';
import type { UIMessage } from 'ai';
import { DefaultChatTransport } from 'ai';
import { CHAT_CONFIG, STORAGE_KEYS } from '@/lib/constants';
import { MessageBubble } from './MessageBubble';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Send, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

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

/**
 * 범용 ID 생성 헬퍼
 */
function generateId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

/**
 * Storage에서 ID를 가져오거나 없으면 새로 생성하여 저장하는 유틸리티
 * 
 * [Refinement] localStorage 접근 시 보안 설정이나 시크릿 모드 등으로 인한
 * 런타임 에러를 방지하기 위해 try/catch 가드를 적용했습니다.
 */
function getOrCreateStoredId(storageKey: string, prefix: string): string {
  // 서버 사이드 렌더링 시에는 빈 문자열 반환 (hydration mismatch 방지)
  if (typeof window === 'undefined') return '';

  let id: string | null = null;
  
  // 1. 기존 ID 로드 시도
  try {
    id = localStorage.getItem(storageKey);
  } catch (err) {
    console.warn(`[Storage] Failed to read ${storageKey} from localStorage:`, err);
  }

  // 2. ID가 없으면 생성 후 저장 시도
  if (!id) {
    id = generateId(prefix);
    try {
      localStorage.setItem(storageKey, id);
    } catch (err) {
      // 저장이 실패하더라도 현재 세션에서는 생성된 ID를 사용함
      console.warn(`[Storage] Failed to save ${storageKey} to localStorage:`, err);
    }
  }
  
  return id;
}

export function ChatWindow() {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [input, setInput] = useState('');

  // 0. ID 상태 지연 초기화 (Lazy Initializer)
  const [sessionId, setSessionId] = useState<string>(() => 
    getOrCreateStoredId(STORAGE_KEYS.CHAT_SESSION_ID, 'sess')
  );

  // userId는 컴포넌트 생명주기 동안 변경되지 않으므로 setter 없이 상태로만 유지 (Lint 경고 해결)
  const [userId] = useState<string>(() => 
    getOrCreateStoredId(STORAGE_KEYS.USER_ID, 'user')
  );

  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [alpha, setAlpha] = useState<number>(CHAT_CONFIG.DEFAULT_ALPHA);

  const scrollToBottom = useCallback(() => {
    if (scrollContainerRef.current) {
      const viewport = scrollContainerRef.current.querySelector(
        '[data-radix-scroll-area-viewport]'
      );
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight;
      }
    }
  }, []);

  // useChat 옵션 메모이제이션 (성능 최적화 및 불필요한 effect 방지)
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

  const { messages, sendMessage, status, error, setMessages } = useChat(chatOptions);


  // 2. 세션 변경 시 히스토리 로드 (sessionId 의존성 추가)
  useEffect(() => {
    if (!sessionId) return;
    let ignore = false;

    // 세션이 변경되면 먼저 메시지 창을 비우고 환영 메시지만 남깁니다.
    // 이를 통해 이전 세션의 잔여 메시지가 섞이는 현상을 방지합니다.
    setMessages([WELCOME_MESSAGE]);

    const loadHistory = async () => {
      setIsHistoryLoading(true);
      try {
        const res = await fetch(`/api/chat/history?session_id=${sessionId}`);
        if (ignore) return;

        if (res.ok) {
          const data = await res.json();
          if (ignore) return;

          if (data.messages && data.messages.length > 0) {
            // 백엔드 메시지를 UIMessage 형식으로 변환
            const historyMessages: UIMessage[] = data.messages.map((m: { role: string; content: string; timestamp?: string }, index: number) => ({
              id: `hist-${index}-${sessionId}`,
              role: m.role as 'user' | 'assistant' | 'system' | 'data',
              parts: [{ type: 'text', text: m.content }],
              createdAt: m.timestamp ? new Date(m.timestamp) : undefined,
            }));

            setMessages(prev => {
              // 환영 메시지와 로딩 중 이미 발생했을 수 있는 신규 메시지는 보존
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
          console.error('Failed to load chat history:', err);
          toast.error('대화 내역을 불러오는데 실패했습니다.', {
            description: errMsg,
          });
        }
      } finally {
        if (!ignore) {
          setIsHistoryLoading(false);
        }
      }
    };

    loadHistory();
    return () => {
      ignore = true;
      setIsHistoryLoading(false); // Cleanup 시 로딩 상태 해제 보장
    };
  }, [sessionId, setMessages]);

  const handleClearHistory = async () => {
    if (!sessionId) return;
    if (!confirm('대화 내용을 모두 초기화하시겠습니까?')) return;

    try {
      const res = await fetch(`/api/chat/history?session_id=${sessionId}`, {
        method: 'DELETE',
      });
      
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.error || 'Failed to clear history');
      }

      // Clear local state and localStorage to get a new session
      const newSid = generateId('sess');
      try {
        localStorage.setItem(STORAGE_KEYS.CHAT_SESSION_ID, newSid);
      } catch (err) {
        console.warn('[Storage] Failed to update session_id in localStorage:', err);
      }
      setSessionId(newSid);
      setMessages([WELCOME_MESSAGE]);
      toast.success('대화가 초기화되었습니다.');
    } catch (err: unknown) {
      console.error('Clear history error:', err);
      const errMsg = err instanceof Error ? err.message : 'Unknown error';
      toast.error('초기화 중 오류가 발생했습니다.', {
        description: errMsg,
      });
    }
  };

  const isLoading = status === 'streaming' || status === 'submitted';

  // 새 메시지 수신 시 자동 스크롤
  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, scrollToBottom]);

  const handleSubmit = useCallback(
    (e?: React.FormEvent) => {
      e?.preventDefault();
      const trimmed = input.trim();
      if (!trimmed || isLoading) return;

      sendMessage({ role: 'user', parts: [{ type: 'text', text: trimmed }] });
      setInput('');
    },
    [input, isLoading, sendMessage]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] w-full max-w-6xl mx-auto border border-slate-200 rounded-2xl shadow-sm bg-slate-50/50 overflow-hidden relative">
      {/* 헤더 */}
      <div className="bg-white/80 backdrop-blur-md border-b px-6 py-4 flex items-center justify-between shadow-sm z-10 sticky top-0">
        <div>
          <h2 className="text-lg font-bold text-slate-800 tracking-tight">Flownote AI</h2>
          <p className="text-xs text-slate-500 font-medium">사용자 데이터 기반 RAG 에이전트</p>
        </div>
        <div className="flex items-center gap-3">
          {/* 하이브리드 가중치 조절 (간이) */}
          <div className="hidden md:flex flex-col items-end mr-2">
            <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Alpha (Dense/FAISS)</span>
            <select 
              value={alpha} 
              aria-label="Alpha weighting for hybrid search"
              onChange={(e) => setAlpha(parseFloat(e.target.value))}
              className="text-xs bg-transparent border-none focus:ring-0 text-slate-600 font-medium cursor-pointer"
            >
              <option value="0.0">0.0 (Keyword Only)</option>
              <option value="0.3">0.3 (Keyword Heavy)</option>
              <option value="0.5">0.5 (Balanced)</option>
              <option value="0.7">0.7 (Semantic Heavy)</option>
              <option value="1.0">1.0 (Semantic Only)</option>
            </select>
          </div>

          <Button 
            variant="ghost" 
            size="sm" 
            onClick={handleClearHistory}
            className="text-slate-400 hover:text-red-500 hover:bg-red-50 text-xs h-8"
          >
            초기화
          </Button>

          {/* 상태 표시 */}
          {(isLoading || isHistoryLoading) && (
            <div className="flex items-center gap-1.5 text-xs text-blue-500 bg-blue-50 px-2.5 py-1 rounded-full border border-blue-100">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>{isHistoryLoading ? '이전 대화 로드 중...' : '응답 생성 중...'}</span>
            </div>
          )}
        </div>
      </div>

      {/* 메시지 목록 */}
      <ScrollArea className="flex-1 w-full" ref={scrollContainerRef}>
        <div className="flex flex-col gap-0 w-full max-w-4xl mx-auto p-4 py-8">
          {messages.map((m: UIMessage) => (
            <MessageBubble key={m.id} message={m} />
          ))}

          {error && (
            <div className="text-center text-sm text-red-600 bg-red-50 p-4 rounded-xl border border-red-100 max-w-md mx-auto my-6 shadow-sm">
              <span className="font-semibold block mb-1">통신 에러 발생</span>
              {error.message || '네트워크 연결이 지연되고 있습니다.'}
            </div>
          )}

          {/* 스크롤 앵커 */}
          <div className="h-4" />
        </div>
      </ScrollArea>

      {/* 입력 영역 */}
      <div className="p-4 bg-white/80 backdrop-blur-md border-t border-slate-200 sticky bottom-0 z-10 w-full">
        <form
          onSubmit={handleSubmit}
          className="max-w-4xl mx-auto flex gap-4 items-end"
        >
          <div className="relative w-full shadow-sm rounded-xl">
            <Textarea
              id="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="메시지를 입력하세요 (Shift + Enter로 줄바꿈)..."
              className="w-full resize-none pr-12 bg-white rounded-xl border-slate-200 focus-visible:ring-1 focus-visible:ring-slate-400 min-h-[56px] max-h-40 text-base py-4"
              rows={1}
              disabled={isLoading}
            />
            <Button
              type="submit"
              size="icon"
              disabled={!input.trim() || isLoading}
              className="absolute right-3 bottom-3 h-8 w-8 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white transition-opacity disabled:opacity-50"
              aria-label="메시지 전송"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4 ml-0.5" />
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

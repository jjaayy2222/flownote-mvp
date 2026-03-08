'use client';

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { useChat } from '@ai-sdk/react';
import type { UIMessage } from 'ai';
import { DefaultChatTransport } from 'ai';
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

function generateSessionId(): string {
  return `sess-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export function ChatWindow() {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<string>('');
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [alpha, setAlpha] = useState(0.5);

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

  const { messages, sendMessage, status, error, setMessages } = useChat({
    messages: [WELCOME_MESSAGE],
    transport: defaultChatTransport,
    // @ts-expect-error - body is supported at runtime but may have type conflicts with custom transport
    body: {
      session_id: sessionId,
      alpha: alpha,
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
  });

  // 1. 초기 세션 복원/생성 (마운트 시 1회)
  useEffect(() => {
    let sid = localStorage.getItem('flownote_chat_session_id');
    if (!sid) {
      sid = generateSessionId();
      localStorage.setItem('flownote_chat_session_id', sid);
    }
    setSessionId(sid);
  }, []);

  // 2. 세션 변경 시 히스토리 로드 (sessionId 의존성 추가)
  useEffect(() => {
    if (!sessionId) return;
    let ignore = false;

    const loadHistory = async () => {
      setIsHistoryLoading(true);
      try {
        const res = await fetch(`/api/chat?session_id=${sessionId}`);
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
              // 현재 세션의 히스토리가 이미 포함되어 있는지 정밀 체크 (ID와 세션 매칭)
              const alreadyHasCurrentHistory = prev.some(m => m.id.endsWith(`-${sessionId}`));
              if (alreadyHasCurrentHistory) return prev;

              // welcome 메시지는 최상단 고정을 위해 제외하고 히스토리 뒤에 대화 재결합
              const currentMessages = prev.filter(m => m.id !== 'welcome');
              return [WELCOME_MESSAGE, ...historyMessages, ...currentMessages];
            });
          }
        }
      } catch (err) {
        if (!ignore) {
          console.error('Failed to load chat history:', err);
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
      setIsHistoryLoading(false); // 세션 전환 시 로딩 상태 강제 초기화 (Stuck 방지)
    };
  }, [sessionId, setMessages]);

  const handleClearHistory = async () => {
    if (!sessionId) return;
    if (!confirm('대화 내용을 모두 초기화하시겠습니까?')) return;

    try {
      await fetch(`/api/chat/history?session_id=${sessionId}`, {
        method: 'DELETE',
      });
      // Clear local state and localStorage to get a new session
      const newSid = generateSessionId();
      localStorage.setItem('flownote_chat_session_id', newSid);
      setSessionId(newSid);
      setMessages([WELCOME_MESSAGE]);
      toast.success('대화가 초기화되었습니다.');
    } catch (err) {
      console.error('Clear history error:', err);
      toast.error('초기화 중 오류가 발생했습니다.');
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

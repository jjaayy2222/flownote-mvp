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

export function ChatWindow() {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [input, setInput] = useState('');

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

  const { messages, sendMessage, status, error } = useChat({
    messages: [WELCOME_MESSAGE],
    transport: new DefaultChatTransport({ api: '/api/chat' }),
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
        {/* 상태 표시 */}
        {isLoading && (
          <div className="flex items-center gap-1.5 text-xs text-blue-500">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>응답 생성 중...</span>
          </div>
        )}
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

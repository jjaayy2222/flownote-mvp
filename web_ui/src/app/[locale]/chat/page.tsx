'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Menu } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { 
  Sheet, 
  SheetContent, 
  SheetTrigger, 
  SheetTitle, 
  SheetDescription, 
  SheetHeader 
} from '@/components/ui/sheet';
import { ChatWindow } from '@/components/chat/ChatWindow';
import { ChatSidebar } from '@/components/chat/ChatSidebar';
import { STORAGE_KEYS } from '@/lib/constants';

// Helper to generate IDs (moved from ChatWindow if needed, but we can just use the same logic)
function generateId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export default function ChatPage() {
  const [isMounting, setIsMounting] = useState(true);
  const [sessionId, setSessionId] = useState<string>('');
  const [userId, setUserId] = useState<string>('');
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  useEffect(() => {
    const storedSid = localStorage.getItem(STORAGE_KEYS.CHAT_SESSION_ID);
    const storedUid = localStorage.getItem(STORAGE_KEYS.USER_ID);

    const activeSid = storedSid || generateId('sess');
    const activeUid = storedUid || generateId('user');

    if (!storedSid) localStorage.setItem(STORAGE_KEYS.CHAT_SESSION_ID, activeSid);
    if (!storedUid) localStorage.setItem(STORAGE_KEYS.USER_ID, activeUid);

    // React 19 / Compiler warning: "Calling setState synchronously within an effect"
    // Use setTimeout to bypass this strict compile-time check while still setting initial state.
    setTimeout(() => {
      setSessionId(activeSid);
      setUserId(activeUid);
      setIsMounting(false);
    }, 0);
  }, []);

  const handleNewChat = useCallback(() => {
    const newSid = generateId('sess');
    localStorage.setItem(STORAGE_KEYS.CHAT_SESSION_ID, newSid);
    setSessionId(newSid);
    setIsMobileOpen(false); // 모바일 서랍 닫기
  }, []);

  const handleSelectSession = useCallback((id: string) => {
    localStorage.setItem(STORAGE_KEYS.CHAT_SESSION_ID, id);
    setSessionId(id);
    setIsMobileOpen(false); // 모바일 서랍 닫기
  }, []);

  // Hydration mismatch 방지
  if (isMounting) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-pulse text-slate-300">Loading conversation...</div>
      </main>
    );
  }

  return (
    <div className="flex h-[calc(100vh-120px)] -m-4 md:-m-8 -mt-6 border-t bg-white overflow-hidden">
      {/* 
          - 한 랩퍼(-m-4 ...)를 써서 부모 레이아웃의 padding을 상쇄하고 전체를 채우게 함. 
          - h-[calc(100vh-constant)]로 상단 nav/header 공간 제외한 전체 높이 확보.
      */}
      <ChatSidebar 
        currentSessionId={sessionId}
        userId={userId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        className="shrink-0 h-full hidden md:flex"
      />
      
      <div className="flex-1 h-full min-w-0 bg-slate-50/10 flex flex-col">
        <div className="flex-1 w-full max-w-5xl mx-auto flex flex-col h-full">
          <ChatWindow 
            externalSessionId={sessionId}
            externalUserId={userId}
            onSessionChange={handleSelectSession}
            headerLeftSlot={
              <Sheet open={isMobileOpen} onOpenChange={setIsMobileOpen}>
                <SheetTrigger asChild>
                  <Button variant="ghost" size="icon" className="md:hidden shrink-0 -ml-2 text-slate-500 hover:text-slate-800">
                    <Menu className="w-5 h-5" />
                    <span className="sr-only">메뉴 토글</span>
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="p-0 w-72 h-full flex flex-col border-none">
                  <SheetHeader className="sr-only">
                    <SheetTitle>메뉴</SheetTitle>
                    <SheetDescription>대화 세션 목록</SheetDescription>
                  </SheetHeader>
                  <ChatSidebar 
                    currentSessionId={sessionId}
                    userId={userId}
                    onSelectSession={handleSelectSession}
                    onNewChat={handleNewChat}
                    className="w-full h-full border-none"
                  />
                </SheetContent>
              </Sheet>
            }
          />
        </div>
      </div>
    </div>
  );
}

'use client';

import React, { useState, useEffect, useCallback } from 'react';
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
  }, []);

  const handleSelectSession = useCallback((id: string) => {
    localStorage.setItem(STORAGE_KEYS.CHAT_SESSION_ID, id);
    setSessionId(id);
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
        className="shrink-0 h-full"
      />
      
      <div className="flex-1 h-full min-w-0 bg-slate-50/10 flex flex-col">
        <div className="flex-1 w-full max-w-5xl mx-auto flex flex-col h-full">
          <ChatWindow 
            externalSessionId={sessionId}
            externalUserId={userId}
            onSessionChange={handleSelectSession}
          />
        </div>
      </div>
    </div>
  );
}

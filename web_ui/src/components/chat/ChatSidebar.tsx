'use client';

import React, { useState, useEffect } from 'react';
import { 
  Plus, 
  MessageSquare, 
  Trash2, 
  Edit2, 
  Clock, 
  Search,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogFooter,
  DialogTrigger 
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface ChatSessionMeta {
  session_id: string;
  name?: string;
  preview?: string;
  last_active_at: string;
  created_at: string;
}

interface ChatSidebarProps {
  currentSessionId: string;
  userId: string;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  className?: string;
}

export function ChatSidebar({ 
  currentSessionId, 
  userId, 
  onSelectSession, 
  onNewChat,
  className 
}: ChatSidebarProps) {
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // 세션 목록 로드
  const fetchSessions = React.useCallback(async () => {
    if (!userId) return;
    setIsLoading(true);
    try {
      const res = await fetch(`/api/chat/sessions?user_id=${userId}`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch (err: unknown) {
      console.error('[ChatSidebar] Failed to fetch sessions:', err);
    } finally {
      setIsLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions, currentSessionId]);

  // 세션 삭제
  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm('이 대화 세션을 삭제하시겠습니까?')) return;

    try {
      const res = await fetch(`/api/chat/history/${sessionId}?user_id=${userId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        toast.success('세션이 삭제되었습니다.');
        setSessions(prev => prev.filter(s => s.session_id !== sessionId));
        if (currentSessionId === sessionId) {
          onNewChat();
        }
      } else {
        throw new Error('Failed to delete session');
      }
    } catch (err: unknown) {
      console.error(err);
      toast.error('세션 삭제 중 오류가 발생했습니다.');
    }
  };

  // 세션 이름 수정
  const handleRenameSession = async (sessionId: string, newName: string) => {
    try {
      const res = await fetch(`/api/chat/sessions/${sessionId}/name`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName }),
      });
      if (res.ok) {
        setSessions(prev => prev.map(s => s.session_id === sessionId ? { ...s, name: newName } : s));
        toast.success('이름이 수정되었습니다.');
      }
    } catch (err: unknown) {
      console.error(err);
      toast.error('이름 수정 실패');
    }
  };

  // 시간순 그룹화
  const filteredSessions = sessions.filter(s => 
    (s.name?.toLowerCase().includes(searchQuery.toLowerCase()) || 
     s.preview?.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const formatDistanceToNow = (dateStr: string) => {
    const now = new Date();
    const date = new Date(dateStr);
    const diffInMs = now.getTime() - date.getTime();
    const diffInHours = diffInMs / (1000 * 60 * 60);

    if (diffInHours < 24 && now.getDate() === date.getDate()) return '오늘';
    if (diffInHours < 48) return '어제';
    if (diffInHours < 24 * 7) return `${Math.floor(diffInHours / 24)}일 전`;
    return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
  };

  const groupedSessions: Record<string, ChatSessionMeta[]> = {};
  filteredSessions.forEach(s => {
    const label = formatDistanceToNow(s.last_active_at);
    if (!groupedSessions[label]) groupedSessions[label] = [];
    groupedSessions[label].push(s);
  });

  return (
    <div 
      className={cn(
        "flex flex-col border-r bg-white transition-all duration-300 relative",
        isCollapsed ? "w-16" : "w-72",
        className
      )}
    >
      <button 
        onClick={() => setIsCollapsed(!isCollapsed)}
        aria-label={isCollapsed ? "사이드바 펼치기" : "사이드바 접기"}
        className="absolute -right-3 top-10 z-20 bg-white border rounded-full p-1 shadow-sm hover:bg-slate-50 md:flex hidden"
      >
        {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>

      <div className="p-4 flex flex-col gap-4">
        <Button 
          onClick={onNewChat} 
          className={cn(
            "w-full flex items-center justify-center gap-2 font-bold",
            isCollapsed ? "p-0 h-10 w-10 mx-auto" : "h-11"
          )}
          variant="outline"
        >
          <Plus size={18} />
          {!isCollapsed && <span>새 대화</span>}
        </Button>

        {!isCollapsed && (
          <div className="relative">
            <Search className="absolute left-3 top-2.5 text-slate-400" size={16} />
            <Input 
              placeholder="세션 검색..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-9 bg-slate-50/50 border-none focus-visible:ring-1 focus-visible:ring-slate-300"
            />
          </div>
        )}
      </div>

      <ScrollArea className="flex-1 px-2">
        {isLoading && sessions.length === 0 ? (
          <div className="flex flex-col gap-2 p-2">
            {[1, 2, 3].map(i => <div key={i} className="h-12 bg-slate-50 rounded-lg animate-pulse" />)}
          </div>
        ) : (
          <div className="flex flex-col gap-6 py-2">
            {Object.entries(groupedSessions).map(([group, items]) => (
              <div key={group} className="flex flex-col gap-1">
                {!isCollapsed && (
                  <h3 className="px-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 flex items-center gap-2">
                    <Clock size={10} />
                    {group}
                  </h3>
                )}
                {items.map(session => (
                  <div
                    key={session.session_id}
                    onClick={() => onSelectSession(session.session_id)}
                    className={cn(
                      "group flex items-center gap-3 px-3 py-3 rounded-xl cursor-pointer transition-all relative overflow-hidden",
                      currentSessionId === session.session_id 
                        ? "bg-slate-100/80 text-slate-800 font-semibold ring-1 ring-slate-200" 
                        : "hover:bg-slate-50 text-slate-500 hover:text-slate-700"
                    )}
                  >
                    <MessageSquare size={18} className={cn(
                      "shrink-0",
                      currentSessionId === session.session_id ? "text-slate-800" : "text-slate-400 group-hover:text-slate-600"
                    )} />
                    
                    {!isCollapsed && (
                      <div className="flex flex-col overflow-hidden w-full pr-6">
                        <span className="text-sm truncate leading-tight">
                          {session.name || '새 대화'}
                        </span>
                        <span className="text-[11px] opacity-60 truncate">
                          {session.preview || '내용 없음'}
                        </span>
                      </div>
                    )}

                    {!isCollapsed && (
                      <div className="flex items-center gap-1 absolute right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Dialog>
                          <DialogTrigger asChild>
                              <button 
                                onClick={(e) => e.stopPropagation()}
                                aria-label="이름 수정"
                                className="p-1 hover:text-slate-800"
                              >
                                <Edit2 size={14} />
                              </button>
                          </DialogTrigger>
                          <DialogContent onClick={(e) => e.stopPropagation()}>
                            <DialogHeader>
                              <DialogTitle>세션 이름 수정</DialogTitle>
                            </DialogHeader>
                            <div className="py-2">
                              <Input 
                                defaultValue={session.name || '새 대화'} 
                                id={`rename-${session.session_id}`}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    const val = (e.currentTarget as HTMLInputElement).value;
                                    handleRenameSession(session.session_id, val);
                                  }
                                }}
                              />
                            </div>
                            <DialogFooter>
                              <Button variant="outline" onClick={() => {
                                // Manual close is tricky with shadcn Dialog without state, 
                                // but standard behavior is fine.
                              }}>취소</Button>
                              <Button onClick={() => {
                                const input = document.getElementById(`rename-${session.session_id}`) as HTMLInputElement;
                                if (input) handleRenameSession(session.session_id, input.value);
                              }}>저장</Button>
                            </DialogFooter>
                          </DialogContent>
                        </Dialog>

                        <button 
                          onClick={(e) => handleDeleteSession(e, session.session_id)}
                          aria-label="세션 삭제"
                          className="p-1 hover:text-red-500"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))}
            
            {!isLoading && filteredSessions.length === 0 && !isCollapsed && (
              <div className="text-center py-10 px-4">
                <p className="text-xs text-slate-400">대화 내역이 없습니다.</p>
              </div>
            )}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}

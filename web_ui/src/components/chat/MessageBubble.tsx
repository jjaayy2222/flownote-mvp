'use client';

import React, { useState, useMemo, memo, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UIMessage } from 'ai';
import { SourcePanel } from './SourcePanel';
import { type SourceItem } from '@/types/chat';
import type { Components } from 'react-markdown';
import { stabilizeIncompleteMarkdown } from '@/lib/markdown';
import { 
  CITATION_VALIDATION_REGEX, 
  extractSources,
  buildProcessedContent,
  areTextPartsEqual,
  areSourcesEqual
} from '@/lib/chat-utils';

/** 백엔드 FeedbackRating 타입과 동기화 */
type FeedbackRating = 'up' | 'down' | 'none';

/** 피드백 API 요청 바디 */
interface FeedbackPayload {
  session_id: string;
  message_id: string;
  rating: FeedbackRating;
  feedback_text?: string;
}

interface MessageBubbleProps {
  message: UIMessage;
  isLast?: boolean;
  isStreaming?: boolean;
  /** 피드백 API 호출에 필요한 세션 ID */
  sessionId?: string;
}

// react-markdown v10 code 컴포넌트 타입
type CodeProps = React.ComponentPropsWithoutRef<'code'> & {
  inline?: boolean;
};

/**
 * [Pure Function] 스트리밍 상태를 고려하여 렌더링 가능한 마크다운 보장
 */
function ensureRenderableMarkdown(markdown: string, shouldPatch: boolean): string {
  return shouldPatch ? stabilizeIncompleteMarkdown(markdown) : markdown;
}

/**
 * [Refactoring] 유효하지 않거나 누락된 인용 소스에 대한 일관된 폴백 렌더러
 */
function FallbackCitation({ 
  children, 
  className, 
  title = "출처 정보 없음" 
}: { 
  children: React.ReactNode; 
  className?: string; 
  title?: string;
}) {
  return (
    <span className={cn("text-slate-500 font-medium cursor-help", className)} title={title}>
      {children}
    </span>
  );
}

/**
 * [Pure Function] MessageBubble의 props 동등성 비교
 * [PR 리뷰 반영] 간결하고 명확한 도메인 헬퍼 기반으로 분리하여 인지 부하 감소
 */
function areMessageBubblePropsEqual(prev: MessageBubbleProps, next: MessageBubbleProps): boolean {
  // 1. 상태 전이 핵심 지표 (스트리밍 종료 시점에 꼭 리렌더링되어야 함)
  if (prev.isLast !== next.isLast) return false;
  if (prev.isStreaming !== next.isStreaming) return false;
  // 2. sessionId 변경 시 재렌더링 필요 (피드백 API 연동 기준값)
  if (prev.sessionId !== next.sessionId) return false;

  // 3. 메시지 객체 참조 동일성 (가장 빠른 레퍼런스 체크)
  if (prev.message === next.message) return true;

  // 4. 메시지 ID 또는 역할 동일성 (역할 변경 시 스타일이 바뀌어야 함)
  if (prev.message.id !== next.message.id) return false;
  if (prev.message.role !== next.message.role) return false;
  
  // 5. 의미적 콘텐츠 동등성 (텍스트 파트 및 소스 리스트)
  if (!areTextPartsEqual(prev.message.parts, next.message.parts)) return false;
  if (!areSourcesEqual(prev.message.metadata, next.message.metadata)) return false;

  return true;
}

/**
 * [Refactoring] 피드백 버튼 컴포넌트 분리 (중복 제거 및 ARIA 타입 캐스팅 해소)
 */
interface FeedbackButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  isActive: boolean;
  activeClassName: string;
  inactiveClassName?: string;
  icon: React.ComponentType<{ className?: string }>;
}

function FeedbackButton({
  isActive,
  activeClassName,
  inactiveClassName = "text-slate-400",
  icon: Icon,
  className,
  ...props
}: FeedbackButtonProps) {
  return (
    <button
      {...props}
      type="button"
      // [A11y] Edge Tools Linter가 동적 중괄호 평가식({expression})을 에러로 잡는 문제를 우회하기 위한 기법
      {...({ 'aria-pressed': isActive })}
      className={cn(
        "p-1.5 rounded-md transition-all duration-200 outline-none",
        "hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed",
        isActive ? activeClassName : inactiveClassName,
        className
      )}
    >
      <Icon className={cn("w-4 h-4", isActive && "fill-current")} />
    </button>
  );
}

/**
 * [Issue #777] 싫어요 클릭 시 추가 의견을 입력받는 Dialog 컴포넌트
 */
interface FeedbackDialogProps {
  isOpen: boolean;
  onSubmit: (text: string) => void;
  onDismiss: () => void;
}

function FeedbackDialog({ isOpen, onSubmit, onDismiss }: FeedbackDialogProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Dialog가 열릴 때 textarea에 포커스
  React.useEffect(() => {
    if (isOpen) {
      setText('');
      // 다음 렌더 사이클에 포커스 (애니메이션 완료 후)
      const timer = setTimeout(() => textareaRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(text.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onDismiss();
  };

  return (
    // Backdrop
    <div
      role="dialog"
      aria-modal="true"
      aria-label="피드백 의견 입력"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={(e) => { if (e.target === e.currentTarget) onDismiss(); }}
      onKeyDown={handleKeyDown}
    >
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-5 animate-in zoom-in-90 duration-150">
        <h3 className="text-sm font-bold text-slate-800 mb-1">아쉬운 점을 알려주세요</h3>
        <p className="text-xs text-slate-500 mb-3">의견을 남겨주시면 AI 개선에 도움이 됩니다. (선택사항)</p>
        <form onSubmit={handleSubmit}>
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="예: 답변이 부정확해요, 더 자세히 설명해주세요..."
            maxLength={1000}
            rows={3}
            className="w-full text-sm rounded-lg border border-slate-200 p-3 resize-none focus:outline-none focus:ring-2 focus:ring-red-300 placeholder:text-slate-400"
          />
          <p className="text-[10px] text-slate-400 text-right mb-3">{text.length}/1000</p>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={onDismiss}
              className="text-xs px-3 py-1.5 rounded-lg text-slate-500 hover:bg-slate-100 transition-colors"
            >
              건너뛰기
            </button>
            <button
              type="submit"
              className="text-xs px-4 py-1.5 rounded-lg bg-red-500 text-white font-medium hover:bg-red-600 transition-colors"
            >
              전송
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export const MessageBubble = memo(
  function MessageBubble({ message, isLast = false, isStreaming = false, sessionId }: MessageBubbleProps) {
    const isUser = message.role === 'user';

  // [Optimization] 소스 추출을 useMemo로 감싸고 헬퍼 함수 활용
  const sources = useMemo(() => extractSources(message.metadata), [message.metadata]);

  // Slide-over 상태
  const [selectedSource, setSelectedSource] = useState<SourceItem | null>(null);
  const [isPanelOpen, setIsPanelOpen] = useState(false);

  // 피드백 상태 (좋아요/싫어요/클릭안함)
  const [feedback, setFeedback] = useState<FeedbackRating>('none');
  // API 호출 중 상태 (Optimistic UI를 위해 별도 관리)
  const [isFeedbackPending, setIsFeedbackPending] = useState(false);
  // 싫어요 클릭 시 의견 입력 Dialog
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  // 디바운스용 타이머 ref (연속 클릭 방지)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 가장 최근 요청을 추적하기 위한 ref (경쟁 조건 방지)
  const latestRatingRef = useRef<FeedbackRating>('none');

  /**
   * [Issue #777] 피드백 API 호출 (Optimistic UI + 디바운스 + 에러 시 롤백)
   */
  const submitFeedbackApi = useCallback(async (
    rating: FeedbackRating,
    feedbackText?: string
  ) => {
    // session_id, message_id 가드
    if (!sessionId || !message.id || message.id === 'welcome') return;

    const payload: FeedbackPayload = {
      session_id: sessionId,
      message_id: message.id,
      rating,
      ...(feedbackText ? { feedback_text: feedbackText } : {}),
    };

    setIsFeedbackPending(true);
    try {
      const res = await fetch('/api/chat/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        // 서버 오류 시 Optimistic UI 롤백
        console.error('[Feedback] API error:', res.status);
        setFeedback((prev) => {
          // 현재 상태가 요청에 의해 변경된 경우에만 롤백
          return latestRatingRef.current === rating ? prev : prev;
        });
      }
    } catch (err) {
      // 네트워크 오류 시 롤백
      console.error('[Feedback] Network error:', err);
    } finally {
      setIsFeedbackPending(false);
    }
  }, [sessionId, message.id]);

  /**
   * 버튼 클릭 핸들러:
   * 1. Optimistic UI: 즉시 상태 업데이트
   * 2. 디바운스 500ms로 연속 클릭 방어
   * 3. 싫어요 → Dialog 노출
   */
  const handleFeedback = useCallback((rating: 'up' | 'down') => {
    // 동일한 평가를 다시 클릭하면 취소(none)으로 토글
    const newRating: FeedbackRating = feedback === rating ? 'none' : rating;

    // [Optimistic UI] 즉시 화면 반영
    setFeedback(newRating);
    latestRatingRef.current = newRating;

    // 싫어요로 변경될 때 Dialog 오픈 (취소가 아닌 경우)
    if (newRating === 'down') {
      setIsDialogOpen(true);
      // Dialog를 통해 API 호출하므로 여기서는 디바운스 제출 생략
      return;
    }

    // [Debounce] 이전 예약 취소 후 500ms 뒤에 API 호출
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      submitFeedbackApi(newRating);
    }, 500);
  }, [feedback, submitFeedbackApi]);

  /** 싫어요 Dialog에서 '전송' 클릭 */
  const handleDialogSubmit = useCallback((text: string) => {
    setIsDialogOpen(false);
    submitFeedbackApi('down', text || undefined);
  }, [submitFeedbackApi]);

  /** 싫어요 Dialog에서 '건너뛰기' 클릭 */
  const handleDialogDismiss = useCallback(() => {
    setIsDialogOpen(false);
    // 텍스트 없이 바로 API 호출
    submitFeedbackApi('down');
  }, [submitFeedbackApi]);

  const handleBadgeClick = (src: SourceItem) => {
    setSelectedSource(src);
    setIsPanelOpen(true);
  };

  const handlePanelClose = () => {
    setIsPanelOpen(false);
    setSelectedSource(null);
  };

  // react-markdown v10 code 컴포넌트
  const markdownComponents: Components = {
    code({ className, children, ...props }: CodeProps) {
      const match = /language-(\w+)/.exec(className || '');
      const isBlock = Boolean(match);
      return isBlock ? (
        <SyntaxHighlighter
          style={vscDarkPlus as Record<string, React.CSSProperties>}
          language={match![1]}
          PreTag="div"
          className="rounded-md my-2 text-xs"
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code
          className="bg-black/10 px-1 py-0.5 rounded text-xs font-mono"
          {...props}
        >
          {children}
        </code>
      );
    },
    // 인라인 인용(Citation) 링크 컴포넌트
    a({ children, href, className, ...props }) {
      if (href?.startsWith('cite:')) {
        const indexStr = href.replace('cite:', '').trim();

        // [Validation] cite 인덱스 검증
        if (!CITATION_VALIDATION_REGEX.test(indexStr)) {
          return <FallbackCitation className={className}>{children}</FallbackCitation>;
        }

        const index = parseInt(indexStr, 10) - 1;
        const source = sources[index];
        
        if (!source) {
          return <FallbackCitation className={className}>{children}</FallbackCitation>;
        }

        const handleCitationClick = (e: React.MouseEvent | React.KeyboardEvent) => {
          e.preventDefault();
          handleBadgeClick(source);
        };

        return (
          <sup
            role="button"
            tabIndex={0}
            onClick={handleCitationClick}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                handleCitationClick(e as unknown as React.MouseEvent);
              }
            }}
            className="
              inline-flex items-center justify-center
              mx-0.5 px-1 min-w-[1rem] h-4
              bg-blue-50 text-blue-700 font-bold text-[9px]
              rounded border border-blue-200
              cursor-pointer hover:bg-blue-100 hover:border-blue-300
              transition-colors align-top mt-0.5
              select-none focus:outline-none focus:ring-1 focus:ring-blue-400
            "
            title={source.title ? `출처: ${source.title}` : `출처: ${source.id}`}
          >
            {children}
          </sup>
        );
      }
      return (
        <a 
          href={href} 
          className={cn("text-blue-600 underline", className)} 
          target="_blank" 
          rel="noopener noreferrer" 
          {...props}
        >
          {children}
        </a>
      );
    },
  };

  // [Performance] 콘텐츠 가공 및 마크다운 안정화 로직 통합 호출
  const processedContent = useMemo(() => {
    const base = buildProcessedContent(message.parts, isUser);
    return ensureRenderableMarkdown(base, isLast && isStreaming);
  }, [message.parts, isUser, isLast, isStreaming]);

  return (
    <>
      <div className={`flex gap-3 w-full ${isUser ? 'justify-end' : 'justify-start'} mb-5 animate-in fade-in slide-in-from-bottom-2 duration-300`}>
        {/* 아바타 */}
        {!isUser && (
          <Avatar className="w-8 h-8 shrink-0 mt-1 shadow-sm border border-slate-100">
            <AvatarFallback className="bg-blue-100 text-blue-700 text-xs font-bold">AI</AvatarFallback>
          </Avatar>
        )}

        <div className={`flex flex-col gap-2 max-w-[85%] ${isUser ? 'items-end' : 'items-start'}`}>
          {/* 메시지 내용 */}
          <div
            className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
              isUser
                ? 'bg-zinc-800 text-white rounded-br-sm shadow-sm'
                : 'bg-white text-slate-800 rounded-bl-sm shadow-sm border border-slate-100'
            }`}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {processedContent}
            </ReactMarkdown>
          </div>

          {/* 피드백 액션바 (AI 메시지 전용, 환영 메시지 제외) */}
          {!isUser && message.id !== 'welcome' && (
            <div className="flex items-center gap-1.5 px-1 mt-0.5">
              <FeedbackButton
                disabled={isStreaming || isFeedbackPending}
                onClick={() => handleFeedback('up')}
                isActive={feedback === 'up'}
                activeClassName="text-blue-600 bg-blue-50"
                icon={ThumbsUp}
                aria-label="좋은 답변입니다"
                title="좋은 답변입니다"
              />
              <FeedbackButton
                disabled={isStreaming || isFeedbackPending}
                onClick={() => handleFeedback('down')}
                isActive={feedback === 'down'}
                activeClassName="text-red-500 bg-red-50"
                icon={ThumbsDown}
                aria-label="아쉬운 답변입니다"
                title="아쉬운 답변입니다"
              />
            </div>
          )}

          {/* 싫어요 선택 시 의견 입력 Dialog */}
          <FeedbackDialog
            isOpen={isDialogOpen}
            onSubmit={handleDialogSubmit}
            onDismiss={handleDialogDismiss}
          />

          {/* 소스 뱃지 영역 */}
          {!isUser && sources.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-0.5 px-1">
              <span className="text-[10px] text-slate-400 w-full mb-0.5 font-bold uppercase tracking-wider">References</span>
              {sources.map((src, idx) => {
                const displayLabel = src.title
                  || (src.id ? src.id.split('/').pop() : null)
                  || `Doc ${idx + 1}`;
                const scoreLabel =
                  src.score != null ? ` · ${(src.score * 100).toFixed(0)}%` : '';

                return (
                  <Badge
                    key={`${src.id}-${idx}`}
                    variant="outline"
                    onClick={() => handleBadgeClick(src)}
                    className="
                      text-[11px] cursor-pointer select-none
                      bg-white text-slate-600 border-slate-200
                      hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700
                      transition-all duration-150 active:scale-95
                      max-w-[180px] truncate
                    "
                    title={src.title || src.id}
                  >
                    📄 {displayLabel}{scoreLabel}
                  </Badge>
                );
              })}
            </div>
          )}
        </div>

        {isUser && (
          <Avatar className="w-8 h-8 shrink-0 mt-1 shadow-sm border border-zinc-700">
            <AvatarFallback className="bg-zinc-800 text-white text-xs font-bold">ME</AvatarFallback>
          </Avatar>
        )}
      </div>

      <SourcePanel
        source={selectedSource}
        isOpen={isPanelOpen}
        onClose={handlePanelClose}
      />
    </>
  );
  },
  areMessageBubblePropsEqual
);

'use client';

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { UIMessage } from 'ai';
import { SourcePanel, SourceItem } from './SourcePanel';
import type { Components } from 'react-markdown';

interface MessageBubbleProps {
  message: UIMessage;
}

// react-markdown v10 code 컴포넌트 타입
type CodeProps = React.ComponentPropsWithoutRef<'code'> & {
  inline?: boolean;
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  // ai v6: sources는 metadata에서 추출 (route.ts에서 metadata 청크로 전달)
  const metadata = (message.metadata ?? {}) as Record<string, unknown>;
  const rawSources = metadata.sources;
  const sources: SourceItem[] = Array.isArray(rawSources)
    ? (rawSources as unknown[])
        .flat()
        .filter((item): item is SourceItem => typeof item === 'object' && item !== null)
    : [];

  // Slide-over 상태
  const [selectedSource, setSelectedSource] = useState<SourceItem | null>(null);
  const [isPanelOpen, setIsPanelOpen] = useState(false);

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
        const index = parseInt(href.replace('cite:', ''), 10) - 1;
        const source = sources[index];
        
        const handleCitationClick = (e: React.MouseEvent | React.KeyboardEvent) => {
          e.preventDefault();
          if (source) handleBadgeClick(source);
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
            title={source ? `출처: ${source.title || source.id}` : '출처 정보 없음'}
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

  const textContent = (message.parts ?? [])
    .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
    .map((p) => p.text)
    .join('');

  // AI 답변 내 [1], [2] 패턴을 인라인 인용 링크로 변환 (isUser가 아닐 때만 적용)
  // [Robustness] 백틱(`)으로 감싸진 코드 블록 내의 매치는 제외하도록 정규식 개선 (리뷰 반영)
  const processedContent = isUser
    ? textContent
    : textContent.replace(/(`{1,3}[\s\S]*?`{1,3})|\[(\d+)\]/g, (match, code, num) => {
        return code ? code : `[${num}](cite:${num})`;
      });

  return (
    <>
      <div className={`flex gap-3 w-full ${isUser ? 'justify-end' : 'justify-start'} mb-5`}>
        {/* AI 아바타 */}
        {!isUser && (
          <Avatar className="w-8 h-8 shrink-0 mt-1">
            <AvatarFallback className="bg-blue-100 text-blue-700 text-xs font-bold">AI</AvatarFallback>
          </Avatar>
        )}

        <div className={`flex flex-col gap-2 max-w-[85%] ${isUser ? 'items-end' : 'items-start'}`}>
          {/* 메시지 버블 */}
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

          {/* 참조 문서 Source 뱃지 영역 (AI 메시지에만 표시) */}
          {!isUser && sources.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-0.5 px-1">
              <span className="text-xs text-slate-400 w-full mb-0.5">참조 문서</span>
              {sources.map((src, idx) => {
                const displayLabel = src.title
                  || (src.id ? src.id.split('/').pop() || `문서 ${idx + 1}` : `문서 ${idx + 1}`);
                const scoreLabel =
                  src.score != null ? ` · ${(src.score * 100).toFixed(0)}%` : '';

                return (
                  <Badge
                    key={idx}
                    variant="outline"
                    onClick={() => handleBadgeClick(src)}
                    className="
                      text-xs cursor-pointer select-none
                      bg-white text-slate-600 border-slate-200
                      hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700
                      transition-all duration-150 active:scale-95
                      max-w-[180px] truncate
                    "
                    title={`클릭하여 문서 내용 보기: ${src.id || ''}`}
                  >
                    📄 {displayLabel}{scoreLabel}
                  </Badge>
                );
              })}
            </div>
          )}
        </div>

        {/* 사용자 아바타 */}
        {isUser && (
          <Avatar className="w-8 h-8 shrink-0 mt-1">
            <AvatarFallback className="bg-zinc-800 text-white text-xs font-bold">ME</AvatarFallback>
          </Avatar>
        )}
      </div>

      {/* 참조 문서 Slide-over 패널 */}
      <SourcePanel
        source={selectedSource}
        isOpen={isPanelOpen}
        onClose={handlePanelClose}
      />
    </>
  );
}

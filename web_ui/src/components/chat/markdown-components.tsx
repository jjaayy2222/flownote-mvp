import React, { useMemo } from 'react';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { Components } from 'react-markdown';
import { cn } from '@/lib/utils';
import { CITATION_VALIDATION_REGEX } from '@/lib/chat-utils';
import type { SourceItem } from '@/types/chat';

export const REMARK_PLUGINS = [remarkGfm];
export const REHYPE_PLUGINS = [rehypeSanitize];

type CodeProps = React.ComponentPropsWithoutRef<'code'> & {
  inline?: boolean;
};

/**
 * 유효하지 않거나 누락된 인용 소스에 대한 일관된 폴백 렌더러
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
 * MessageBubble 및 ChatWindow(스트리밍 렌더링)에서 공통으로 사용할 마크다운 컴포넌트들을 생성합니다.
 * - 소스(sources) 데이터와 클릭 핸들러(onBadgeClick)는 인용구 렌더링에 사용됩니다.
 */
export function useMarkdownComponents(
  sources?: SourceItem[],
  onBadgeClick?: (src: SourceItem) => void
): Components {
  return useMemo(() => {
    const safeSources = sources ?? [];

    return {
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
            className={cn("bg-black/10 px-1 py-0.5 rounded text-xs font-mono", className)}
            {...props}
          >
            {children}
          </code>
        );
      },
      a({ children, href, className, ...props }) {
        if (href?.startsWith('cite:')) {
          const indexStr = href.replace('cite:', '').trim();

          if (!CITATION_VALIDATION_REGEX.test(indexStr)) {
            return <FallbackCitation className={className}>{children}</FallbackCitation>;
          }

          const index = parseInt(indexStr, 10) - 1;
          const source = safeSources[index];
          
          if (!source) {
            return <FallbackCitation className={className}>{children}</FallbackCitation>;
          }

          const commonBadgeClasses = "inline-flex items-center justify-center mx-0.5 px-1 min-w-[1rem] h-4 rounded align-top mt-0.5 select-none";
          
          if (!onBadgeClick) {
            return (
              <sup
                className={cn(commonBadgeClasses, "bg-slate-100 text-slate-500 font-medium text-[9px] border border-slate-200")}
                title={source.title ? `출처: ${source.title}` : `출처: ${source.id}`}
              >
                {children}
              </sup>
            );
          }

          const handleCitationAction = (e: React.SyntheticEvent) => {
            e.preventDefault();
            onBadgeClick(source);
          };

          return (
            <sup
              role="button"
              tabIndex={0}
              onClick={handleCitationAction}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  handleCitationAction(e);
                }
              }}
              className={cn(
                commonBadgeClasses,
                "bg-blue-50 text-blue-700 font-bold text-[9px] border border-blue-200",
                "cursor-pointer hover:bg-blue-100 hover:border-blue-300 transition-colors focus:outline-none focus:ring-1 focus:ring-blue-400"
              )}
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
  }, [sources, onBadgeClick]);
}

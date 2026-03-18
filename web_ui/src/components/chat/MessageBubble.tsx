'use client';

import React, { useState, useMemo, memo } from 'react';
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

/** 
 * [Types] 메시지 파트 중 텍스트 타입 정의 (리뷰 반영) 
 */
type TextPart = { type: 'text'; text: string };

// [Constants] 인용 관련 공용 패턴 및 기본 텍스트
// 중앙 집중화를 통해 정규식 불일치 가능성을 원천 차단했습니다.
const CITATION_ID_FRAGMENT = '(?:[1-9]\\d*)';
const CITATION_VALIDATION_REGEX = new RegExp(`^${CITATION_ID_FRAGMENT}$`);
const INLINE_CITATION_REGEX = new RegExp(
  `(\`{1,3}[\\s\\S]*?\`{1,3})|\\[(${CITATION_ID_FRAGMENT})\\](?!\\s*[\\(:])`,
  'g'
);
const DEFAULT_FALLBACK_TITLE = "출처 정보 없음";

/** 
 * [Pure Function] 텍스트 파트만 안전하게 추출하는 헬퍼 (리뷰 반영)
 */
function getTextParts(parts: UIMessage['parts'] | undefined): TextPart[] {
  return (parts ?? []).filter(
    (p): p is TextPart =>
      p !== null && typeof p === 'object' && p.type === 'text'
  );
}

/** 
 * [Pure Function] 전체 텍스트 내용만 추출하는 헬퍼 (DRY 원칙)
 * - 실제 문자열이 필요한 렌더링/처리 경로에서만 사용할 것 (리뷰 반영)
 */
function getTextContent(parts: UIMessage['parts']): string {
  return getTextParts(parts).map(p => p.text).join('');
}

/**
 * [Pure Function] 텍스트 내용 고등 동등성 비교 헬퍼 (리뷰 반영)
 * - 비-텍스트 파트는 무시하고 텍스트 내용만 순서대로 비교
 */
function areTextPartsEqual(prev?: UIMessage['parts'], next?: UIMessage['parts']): boolean {
  if (prev === next) return true;

  const prevTextParts = getTextParts(prev);
  const nextTextParts = getTextParts(next);

  if (prevTextParts.length !== nextTextParts.length) return false;

  for (let i = 0; i < prevTextParts.length; i++) {
    if (prevTextParts[i].text !== nextTextParts[i].text) return false;
  }
  return true;
}

/**
 * [Pure Function] 소스 리스트 동등성 비교 도메인 헬퍼 (리뷰 반영)
 * - 메타데이터 구조 가드 및 얕은 배열 비교 수행
 */
function areSourcesEqual(
  prevMeta: UIMessage['metadata'],
  nextMeta: UIMessage['metadata']
): boolean {
  const prevS = (prevMeta as { sources?: unknown[] } | undefined)?.sources;
  const nextS = (nextMeta as { sources?: unknown[] } | undefined)?.sources;

  if (prevS === nextS) return true;
  if (!Array.isArray(prevS) || !Array.isArray(nextS)) return false;
  if (prevS.length !== nextS.length) return false;

  for (let i = 0; i < prevS.length; i++) {
    if (prevS[i] !== nextS[i]) return false;
  }
  return true;
}

/** 
 * [Pure Function] 메타데이터에서 소스 리스트 추출 (리뷰 반영)
 */
function extractSources(metadata: UIMessage['metadata']): SourceItem[] {
  const meta = (metadata as Record<string, unknown> | undefined) ?? {};
  const rawSources = meta.sources;

  return Array.isArray(rawSources)
    ? (rawSources as unknown[])
        .flat()
        .filter((item): item is SourceItem => 
          item !== null && typeof item === 'object' && 'id' in item
        )
    : [];
}

/** 
 * [Pure Function] 텍스트 가공 및 인용 링크 변환 (리뷰 반영)
 */
function buildProcessedContent(parts: UIMessage['parts'], isUser: boolean): string {
  const textContent = getTextContent(parts);

  if (isUser) return textContent;

  return textContent.replace(INLINE_CITATION_REGEX, (match, code, num) => {
    return code ? code : `[${num}](cite:${num})`;
  });
}

/**
 * [Refactoring] 유효하지 않거나 누락된 인용 소스에 대한 일관된 폴백 렌더러
 * 리뷰 코멘트에 따라 툴팁 텍스트를 prop으로 분리하여 재사용성을 높였습니다.
 */
function FallbackCitation({ 
  children, 
  className, 
  title = DEFAULT_FALLBACK_TITLE 
}: { 
  children: React.ReactNode; 
  className?: string; 
  title?: string;
}) {
  return (
    <span className={cn("text-slate-500", className)} title={title}>
      {children}
    </span>
  );
}

export const MessageBubble = memo(
  function MessageBubble({ message }: MessageBubbleProps) {
    const isUser = message.role === 'user';


  // [Optimization] 순수 함수와 useMemo를 결합한 소스 추출 (유지보수성 향상)
  const sources = useMemo(() => extractSources(message.metadata), [message.metadata]);

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
        const indexStr = href.replace('cite:', '').trim();

        // [Validation] cite 인덱스 검증 (중앙 집중화된 정규식 사용)
        if (!CITATION_VALIDATION_REGEX.test(indexStr)) {
          return <FallbackCitation className={className}>{children}</FallbackCitation>;
        }

        const index = parseInt(indexStr, 10) - 1;
        const source = sources[index];
        
        // [Robustness] 소스가 없는 경우 폴백
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

  // [Performance] 순수 함수와 useMemo를 결합한 콘텐츠 변환 (가독성 향상)
  const processedContent = useMemo(
    () => buildProcessedContent(message.parts, isUser),
    [message.parts, isUser]
  );

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
  },
  (prev, next) => {
    // 1. 객체 참조가 같으면 즉시 트루 (가장 빠른 비교)
    if (prev.message === next.message) return true;

    // 2. ID가 다르면 무조건 리렌더링
    if (prev.message.id !== next.message.id) return false;
    
    // 3. [PR 리뷰 반영] 간결하고 명확한 도메인 헬퍼 기반 비교
    if (!areTextPartsEqual(prev.message.parts, next.message.parts)) return false;
    if (!areSourcesEqual(prev.message.metadata, next.message.metadata)) return false;

    return true;
  }
);

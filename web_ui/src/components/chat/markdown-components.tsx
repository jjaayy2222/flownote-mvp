import React, { useMemo, useState, useEffect } from 'react';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { Components } from 'react-markdown';
import { Check, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CITATION_VALIDATION_REGEX } from '@/lib/chat-utils';
import type { SourceItem } from '@/types/chat';

export const REMARK_PLUGINS = [remarkGfm];
export const REHYPE_PLUGINS = [rehypeSanitize];

// 복사 완료 피드백 표시 지속 시간 (ms) — 하드코딩 방지
const COPY_FEEDBACK_DURATION_MS = 2000;

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
 * 코드 블록 복사 버튼 컴포넌트
 *
 * - 복사 성공 시 COPY_FEEDBACK_DURATION_MS 동안 체크마크 피드백 표시 후 원복
 * - copied 상태 변화에 반응하는 단일 useEffect로 타이머를 관리하여
 *   timerRef + useCallback 의존성 복잡성 제거 (컴포넌트 언마운트 시 자동 정리 보장)
 * - 개인정보(PII)를 직접 다루지 않으며, clipboard API를 통해서만 코드 문자열을 처리
 */
function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);

  // copied=true가 되면 타이머를 등록하고, 만료 시 false로 복원.
  // useEffect 클린업이 언마운트 시 타이머를 자동 취소하므로 별도 timerRef 불필요.
  useEffect(() => {
    if (!copied) return;
    const timerId = setTimeout(() => setCopied(false), COPY_FEEDBACK_DURATION_MS);
    return () => clearTimeout(timerId);
  }, [copied]);

  const handleCopy = async () => {
    if (copied) return; // 복사 완료 상태 중 중복 클릭 방지
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      // Clipboard API 실패(권한 거부 등) — 사용자 UX에 영향 없이 조용히 처리
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? '복사 완료' : '코드 복사'}
      title={copied ? '복사 완료!' : '클립보드에 복사'}
      className={cn(
        'absolute top-2 right-2 z-10',
        'flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium',
        'transition-all duration-150',
        copied
          ? 'bg-green-600/80 text-white'
          : 'bg-white/10 text-slate-300 hover:bg-white/20 hover:text-white',
      )}
    >
      {copied ? (
        <>
          <Check className="w-3 h-3" aria-hidden="true" />
          <span>Copied!</span>
        </>
      ) : (
        <>
          <Copy className="w-3 h-3" aria-hidden="true" />
          <span>Copy</span>
        </>
      )}
    </button>
  );
}

/**
 * 코드 블록 렌더링 컴포넌트 (블록 코드 전용)
 *
 * code() 핸들러로부터 블록 렌더링 책임을 분리하여 단일 책임 원칙(SRP)을 준수합니다.
 * - isStreaming=true: plain <pre>로 렌더링 (미완성 코드 펜스 파서 오류 방지)
 * - isStreaming=false: SyntaxHighlighter + CopyButton 활성화 (type:"done" 수신 후)
 */
type CodeBlockProps = {
  language: string;
  codeText: string;
  isStreaming?: boolean;
};

function CodeBlock({ language, codeText, isStreaming }: CodeBlockProps) {
  // [설계 결정] 스트리밍 중에는 plain <pre>로 렌더링
  // 미완성 코드 펜스로 인한 SyntaxHighlighter 파서 오류 및 레이아웃 깨짐 방지
  if (isStreaming) {
    return (
      <pre className="rounded-md my-2 text-xs bg-[#1e1e1e] text-[#d4d4d4] p-4 overflow-x-auto">
        <code>{codeText}</code>
      </pre>
    );
  }

  // 스트리밍 완료(type:"done" 수신) 후: SyntaxHighlighter + 복사 버튼 활성화
  return (
    <div className="relative group/codeblock my-2">
      <CopyButton code={codeText} />
      <SyntaxHighlighter
        style={vscDarkPlus as Record<string, React.CSSProperties>}
        language={language}
        PreTag="div"
        className="rounded-md text-xs !mt-0"
      >
        {codeText}
      </SyntaxHighlighter>
    </div>
  );
}

/**
 * MessageBubble 및 ChatWindow(스트리밍 렌더링)에서 공통으로 사용할 마크다운 컴포넌트들을 생성합니다.
 *
 * @param sources - 인용 소스 목록 (citation badge 렌더링에 사용)
 * @param onBadgeClick - 인용 뱃지 클릭 핸들러
 * @param isStreaming - true이면 코드 블록을 plain <pre>로 렌더링 (스트리밍 중 미완성 코드 펜스 대응)
 *                     false(기본값)이면 SyntaxHighlighter + 복사 버튼을 활성화
 *
 * [설계 결정 - 완료 이벤트 기반 하이라이팅]:
 * 스트리밍 중(isStreaming=true) SyntaxHighlighter를 적용하면 미완성 코드 블록(닫히지 않은 ```)이
 * 파서 오류로 이어져 레이아웃 깨짐이 발생합니다. type:"done" 수신(isStreaming=false) 이후에만
 * 하이라이팅을 적용하여 UX 안정성을 보장합니다.
 */
export function useMarkdownComponents(
  sources?: SourceItem[],
  onBadgeClick?: (src: SourceItem) => void,
  isStreaming?: boolean,
): Components {
  return useMemo(() => {
    const safeSources = sources ?? [];

    return {
      code({ className, children, ...props }: CodeProps) {
        const match = /language-(\w+)/.exec(className || '');
        const isBlock = Boolean(match);
        const codeText = String(children).replace(/\n$/, '');

        if (!isBlock) {
          // 인라인 코드: 항상 일반 스타일 적용 (하이라이팅 불필요)
          return (
            <code
              className={cn("bg-black/10 px-1 py-0.5 rounded text-xs font-mono", className)}
              {...props}
            >
              {children}
            </code>
          );
        }

        // 블록 코드: CodeBlock에 렌더링 책임 위임 (isStreaming에 따른 분기는 CodeBlock 내부에서 처리)
        return (
          <CodeBlock
            language={match![1]}
            codeText={codeText}
            isStreaming={isStreaming}
          />
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
  }, [sources, onBadgeClick, isStreaming]);
}

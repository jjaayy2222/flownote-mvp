import type { UIMessage } from 'ai';
import { SourceItem } from '@/components/chat/SourcePanel';

/**
 * [Constants] 인용 및 텍스트 처리 정규식
 */
export const CITATION_ID_FRAGMENT = '(?:[1-9]\\d*)';
export const CITATION_VALIDATION_REGEX = new RegExp(`^${CITATION_ID_FRAGMENT}$`);
export const INLINE_CITATION_REGEX = new RegExp(
  `(\`{1,3}[\\s\\S]*?\`{1,3})|\\[(${CITATION_ID_FRAGMENT})\\](?!\\s*[\\(:])`,
  'g'
);

/**
 * [Types] 메시지 파트 중 텍스트 타입 정의
 */
export type TextPart = { type: 'text'; text: string };

/**
 * [Pure Function] 텍스트 파트만 안전하게 추출하는 헬퍼
 */
export function getTextParts(parts: UIMessage['parts'] | undefined): TextPart[] {
  return (parts ?? []).filter(
    (p): p is TextPart =>
      p !== null && typeof p === 'object' && p.type === 'text'
  );
}

/**
 * [Pure Function] 전체 텍스트 내용만 추출하는 헬퍼
 */
export function getTextContent(parts: UIMessage['parts'] | undefined): string {
  return getTextParts(parts)
    .map(p => p.text)
    .join('');
}

/**
 * [Pure Function] 텍스트 내용 고등 동등성 비교 헬퍼
 * [PR 리뷰 반영] 제너레이터 대신 원시 배열을 활용하여 로직 단순화
 */
export function areTextPartsEqual(prev?: UIMessage['parts'], next?: UIMessage['parts']): boolean {
  if (prev === next) return true;

  const prevParts = getTextParts(prev);
  const nextParts = getTextParts(next);

  if (prevParts.length !== nextParts.length) return false;
  
  for (let i = 0; i < prevParts.length; i++) {
    if (prevParts[i].text !== nextParts[i].text) return false;
  }
  return true;
}

/**
 * [Pure Function] 소스 리스트 동등성 비교 도메인 헬퍼
 */
export function areSourcesEqual(
  prevMeta: UIMessage['metadata'] | undefined,
  nextMeta: UIMessage['metadata'] | undefined
): boolean {
  const prevS = (prevMeta as { sources?: SourceItem[] } | undefined)?.sources;
  const nextS = (nextMeta as { sources?: SourceItem[] } | undefined)?.sources;

  if (prevS === nextS) return true;
  if (!Array.isArray(prevS) || !Array.isArray(nextS)) return false;
  if (prevS.length !== nextS.length) return false;

  for (let i = 0; i < prevS.length; i++) {
    if (prevS[i] !== nextS[i]) return false;
  }
  return true;
}

/**
 * [Pure Function] 메타데이터에서 소스 리스트 추출
 */
export function extractSources(metadata: UIMessage['metadata'] | undefined): SourceItem[] {
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
 * [Pure Function] 텍스트 가공 및 인용 링크 변환
 */
export function buildProcessedContent(parts: UIMessage['parts'], isUser: boolean): string {
  const textContent = getTextContent(parts);

  if (isUser) return textContent;

  return textContent.replace(INLINE_CITATION_REGEX, (match, code, num) => {
    return code ? code : `[${num}](cite:${num})`;
  });
}

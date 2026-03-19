/**
 * [Type] 채팅에서 참조되는 개별 문서(Source) 아이템의 구조를 정의합니다.
 */
export interface SourceItem {
  id?: string;
  score?: number;
  page_content?: string;
  source?: string;
  title?: string;
  [key: string]: unknown;
}

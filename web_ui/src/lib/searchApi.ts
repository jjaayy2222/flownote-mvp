// web_ui/src/lib/searchApi.ts

import { API_BASE } from '@/lib/api';

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Types — Backend API 스펙과 1:1 대응
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export type PARACategory = 'Projects' | 'Areas' | 'Resources' | 'Archives';

export interface HybridSearchRequest {
  query: string;
  k?: number;              // 반환 결과 수 (1~50, 기본 5)
  alpha?: number;          // Dense 가중치 (0.0~1.0, 기본 0.5)
  category?: PARACategory | null;
  metadata_filter?: Record<string, unknown> | null;
}

export interface SearchResultItem {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
  score: number;
}

export interface HybridSearchResponse {
  status: string;
  query: string;
  results: SearchResultItem[];
  count: number;
  alpha: number;
  applied_filter: Record<string, unknown> | null;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Error types
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export class SearchApiError extends Error {
  constructor(
    public readonly statusCode: number,
    message: string,
  ) {
    super(message);
    this.name = 'SearchApiError';
  }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// API 클라이언트
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/**
 * POST /search/hybrid 를 호출하는 클라이언트
 *
 * 에러 처리:
 *  - 422: 파라미터 유효성 오류 (alpha 범위, 빈 쿼리 등)
 *  - 500: 서버 내부 오류
 *  - 네트워크 오류: fetch 실패 (서버 미실행 등)
 */
export async function hybridSearch(
  request: HybridSearchRequest,
  signal?: AbortSignal,
): Promise<HybridSearchResponse> {
  const url = `${API_BASE}/search/hybrid`;

  const body: HybridSearchRequest = {
    query: request.query.trim(),
    k: request.k ?? 5,
    alpha: request.alpha ?? 0.5,
    category: request.category ?? null,
    metadata_filter: request.metadata_filter ?? null,
  };

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const errJson = await response.json();
      detail = errJson?.detail ?? detail;
    } catch {
      // JSON 파싱 실패 시 기본 메시지 유지
    }
    throw new SearchApiError(response.status, detail);
  }

  return response.json() as Promise<HybridSearchResponse>;
}

export const PARA_CATEGORIES: PARACategory[] = [
  'Projects',
  'Areas',
  'Resources',
  'Archives',
];

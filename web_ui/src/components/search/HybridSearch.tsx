// web_ui/src/components/search/HybridSearch.tsx
'use client';

import React, { useState, useRef, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  hybridSearch,
  SearchApiError,
  SearchResultItem,
  PARACategory,
  PARA_CATEGORIES,
} from '@/lib/searchApi';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Search, Loader2, AlertCircle, FileSearch, Clock, ChevronDown, ChevronUp } from 'lucide-react';

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Constants
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const DEFAULT_K = 5;
const DEFAULT_ALPHA = 0.5;
const LATENCY_WARN_MS = 2000; // 2초 이상이면 "느림" 표시

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Sub-components
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function LatencyBadge({ ms }: { ms: number }) {
  const t = useTranslations('search.status');
  const isWarn = ms >= LATENCY_WARN_MS;
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-mono px-2 py-0.5 rounded-full ${
        isWarn
          ? 'bg-amber-50 text-amber-700 border border-amber-200'
          : 'bg-green-50 text-green-700 border border-green-200'
      }`}
    >
      <Clock className="h-3 w-3" />
      {t('latency_unit', { ms: ms.toLocaleString() })} {isWarn && '⚠️'}
    </span>
  );
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 70
      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
      : pct >= 40
      ? 'bg-blue-50 text-blue-700 border-blue-200'
      : 'bg-slate-50 text-slate-500 border-slate-200';
  return (
    <Badge variant="outline" className={`text-xs font-mono ${color}`}>
      {pct}%
    </Badge>
  );
}

function ResultCard({ item, index }: { item: SearchResultItem; index: number }) {
  const tResult = useTranslations('search.result');
  const tFilters = useTranslations('search.filters');
  const [expanded, setExpanded] = useState(false);
  const source = typeof item.metadata?.source === 'string' ? item.metadata.source : null;
  const category = typeof item.metadata?.category === 'string' ? item.metadata.category : null;
  const isLong = item.content.length > 300;
  const displayContent = isLong && !expanded ? item.content.slice(0, 300) + '...' : item.content;

  return (
    <div
      className="group relative border rounded-xl p-4 bg-white hover:shadow-md transition-all duration-200 hover:border-blue-200"
      data-testid={`search-result-${index}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex-shrink-0 w-6 h-6 rounded-full bg-slate-100 text-slate-500 text-xs font-bold flex items-center justify-center">
            {index + 1}
          </span>
          {source && (
            <span className="text-xs font-mono text-muted-foreground truncate" title={source}>
              {source}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {category && (
            <Badge variant="secondary" className="text-xs">
              {tFilters.has(`categories.${category}`) 
                ? tFilters(`categories.${category}`) 
                : category}
            </Badge>
          )}
          <ScoreBadge score={item.score} />
        </div>
      </div>

      {/* Content */}
      <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap break-words">
        {displayContent}
      </p>

      {isLong && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1 transition-colors"
        >
          {expanded ? (
            <>
              <ChevronUp className="h-3 w-3" /> {tResult('collapse')}
            </>
          ) : (
            <>
              <ChevronDown className="h-3 w-3" /> {tResult('expand')}
            </>
          )}
        </button>
      )}
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Main Component
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export function HybridSearch() {
  const t = useTranslations('search');
  
  // Form state
  const [query, setQuery] = useState('');
  const [k, setK] = useState(DEFAULT_K);
  const [alpha, setAlpha] = useState(DEFAULT_ALPHA);
  const [category, setCategory] = useState<PARACategory | ''>('');

  // UI state
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchResultItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [lastQuery, setLastQuery] = useState<string>('');

  const abortRef = useRef<AbortController | null>(null);

  const handleSearch = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed) return;

    // 이전 요청 취소
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setResults(null);
    setLatencyMs(null);
    setLastQuery(trimmed);

    const startAt = performance.now();

    try {
      const data = await hybridSearch(
        {
          query: trimmed,
          k,
          alpha,
          category: category || null,
        },
        controller.signal,
      );

      const elapsed = Math.round(performance.now() - startAt);
      setLatencyMs(elapsed);
      setResults(data.results);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // 사용자가 취소한 경우 — 에러 표시 불필요
        return;
      }
      if (err instanceof SearchApiError) {
        if (err.statusCode === 422) {
          setError(err.message); // 상세 메시지(파라미터 오류 등)
        } else if (err.statusCode >= 500) {
          setError(t('status.error_server'));
        } else {
          setError(err.message);
        }
      } else if (err instanceof TypeError) {
        // fetch 실패 (네트워크 오류, 서버 미실행 등)
        setError(t('status.error_network'));
      } else {
        setError(t('status.error_unexpected'));
      }
    } finally {
      setLoading(false);
    }
  }, [query, k, alpha, category, t]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !loading) {
      handleSearch();
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    setLoading(false);
  };

  // 컴포넌트 언마운트 시 진행 중인 검색 요청 취소 (Cleanup)
  React.useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // ── Render ──────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Search Form */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-blue-600" />
            {t('title')}
          </CardTitle>
          <CardDescription>
            {t('description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Query Input */}
          <div className="flex gap-2">
            <input
              id="search-query-input"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('placeholder')}
              disabled={loading}
              aria-label={t('title')}
              className="flex-1 px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:opacity-50 disabled:bg-slate-50"
            />
            {loading ? (
              <Button
                id="search-cancel-btn"
                variant="outline"
                onClick={handleCancel}
                className="gap-2 min-w-[80px]"
              >
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('cancel')}
              </Button>
            ) : (
              <Button
                id="search-submit-btn"
                onClick={handleSearch}
                disabled={!query.trim()}
                className="gap-2 min-w-[80px] bg-blue-600 hover:bg-blue-700"
              >
                <Search className="h-4 w-4" />
                {t('submit')}
              </Button>
            )}
          </div>

          {/* Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* 결과 수 */}
            <div className="space-y-1">
              <label htmlFor="search-k-input" className="text-xs text-muted-foreground font-medium">
                {t('filters.k_label')}: <span className="text-blue-600 font-bold">{k}</span>
              </label>
              <input
                id="search-k-input"
                type="range"
                min={1}
                max={20}
                value={k}
                onChange={(e) => setK(Number(e.target.value))}
                disabled={loading}
                className="w-full accent-blue-600"
              />
            </div>

            {/* Alpha (Dense 가중치) */}
            <div className="space-y-1">
              <label htmlFor="search-alpha-input" className="text-xs text-muted-foreground font-medium">
                {t('filters.alpha_label')}: <span className="text-blue-600 font-bold">{alpha.toFixed(1)}</span>
              </label>
              <input
                id="search-alpha-input"
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={alpha}
                onChange={(e) => setAlpha(parseFloat(e.target.value))}
                disabled={loading}
                className="w-full accent-blue-600"
              />
              <div className="flex justify-between text-[10px] text-muted-foreground uppercase font-bold tracking-tighter">
                <span>{t('filters.alpha_hint_sparse')}</span>
                <span className="font-normal lowercase">{t('filters.alpha_hint_mid')}</span>
                <span>{t('filters.alpha_hint_dense')}</span>
              </div>
            </div>

            {/* PARA 카테고리 필터 */}
            <div className="space-y-1">
              <label htmlFor="search-category-select" className="text-xs text-muted-foreground font-medium">
                {t('filters.category_label')}
              </label>
              <select
                id="search-category-select"
                value={category}
                onChange={(e) => setCategory(e.target.value as PARACategory | '')}
                disabled={loading}
                className="w-full px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:opacity-50"
              >
                <option value="">{t('filters.category_all')}</option>
                {PARA_CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {t(`filters.categories.${cat}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-3" aria-live="polite" aria-label={t('status.searching')}>
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="border rounded-xl p-4 bg-white animate-pulse">
              <div className="h-3 bg-slate-200 rounded w-1/3 mb-3" />
              <div className="space-y-2">
                <div className="h-2.5 bg-slate-100 rounded w-full" />
                <div className="h-2.5 bg-slate-100 rounded w-4/5" />
                <div className="h-2.5 bg-slate-100 rounded w-2/3" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Error State */}
      {!loading && error && (
        <div
          role="alert"
          className="flex items-start gap-3 p-4 border border-red-200 rounded-xl bg-red-50 text-red-700"
        >
          <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold text-sm">{t('status.error_title')}</p>
            <p className="text-sm">{error}</p>
          </div>
        </div>
      )}

      {/* Results */}
      {!loading && results !== null && !error && (
        <div className="space-y-3">
          {/* Results Header */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {t('status.results_count', { query: lastQuery, count: results.length })}
            </p>
            {latencyMs !== null && <LatencyBadge ms={latencyMs} />}
          </div>

          {/* Empty State */}
          {results.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground border rounded-xl bg-white">
              <Search className="h-12 w-12 mb-3 opacity-20" />
              <p className="font-medium">{t('status.no_results')}</p>
              <p className="text-sm mt-1">
                {t('status.no_results_hint')}
              </p>
              {category && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-3 text-blue-600"
                  onClick={() => setCategory('')}
                >
                  {t('status.clear_filter')}
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {results.map((item, i) => (
                <ResultCard
                  key={item.metadata?.source ? `${item.metadata.source}-${i}` : i}
                  item={item}
                  index={i}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

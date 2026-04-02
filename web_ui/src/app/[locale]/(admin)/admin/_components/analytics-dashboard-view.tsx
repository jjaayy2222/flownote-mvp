'use client';

import { useState, useTransition } from 'react';
import { useTranslations } from 'next-intl';
import { BellRing, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';

import { FeedbackTrendChart } from './feedback-trend-chart';
import { FeedbackListPanel } from './feedback-list-panel';
import { type FeedbackStatsResponse, triggerTestAlert } from '../analytics/actions';
import { clsx } from 'clsx';


interface AnalyticsViewProps {
  stats: FeedbackStatsResponse;
  total: number;
  upRatio: number;
  downRatio: number;
}

/**
 * [Client Component] 분석 대시보드의 UI 렌더링 담당.
 * - Server Component(page.tsx)에서 데이터를 받아 표시
 * - useTranslations 훅 사용을 위해 Client Component로 분리
 */
export function AnalyticsDashboardView({ stats, total, upRatio, downRatio }: AnalyticsViewProps) {
  const t = useTranslations('admin.analytics');

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('subtitle')}</p>
        </div>

        {/* 시스템 헬스 바 & 테스트 버튼 */}
        <SystemHealthBar 
          isActive={stats.is_monitoring_active} 
          t={t} 
        />
      </div>


      {/* 요약 카드 3개 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label={t('summary.total')}
          value={total}
          colorClass="text-foreground"
        />
        <StatCard
          label={t('summary.up')}
          value={`${stats.total_up} (${upRatio}%)`}
          colorClass="text-emerald-600 dark:text-emerald-400"
        />
        <StatCard
          label={t('summary.down')}
          value={`${stats.total_down} (${downRatio}%)`}
          colorClass="text-rose-500 dark:text-rose-400"
        />
      </div>

      {/* 트렌드 차트 및 피드 리스트 섹션 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-xl border bg-card p-6 shadow-sm">
          <h2 className="mb-4 text-base font-semibold">
            {t('trend_chart.title')}
          </h2>
          <FeedbackTrendChart data={stats.trends} />
        </section>

        <section className="rounded-xl border bg-card p-6 shadow-sm">
          <h2 className="mb-4 text-base font-semibold">
            {t('feed_list.title')}
          </h2>
          <FeedbackListPanel feedbacks={stats.recent_feedbacks} />
        </section>
      </div>
    </div>
  );
}

function SystemHealthBar({ isActive, t }: { isActive: boolean; t: ReturnType<typeof useTranslations> }) {

  const [isPending, startTransition] = useTransition();
  const [lastResult, setLastResult] = useState<{ success: boolean; msg: string } | null>(null);

  const handleTest = () => {
    startTransition(async () => {
      const res = await triggerTestAlert();
      setLastResult({ success: res.success, msg: res.success ? t('health.test_success') : t('health.test_error') });
      setTimeout(() => setLastResult(null), 3000);
    });
  };

  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card/50 p-3 shadow-inner">
      <div className="flex items-center gap-2 pr-3 border-r">
        <div className={clsx(
          "flex h-2 w-2 rounded-full",
          isActive ? "bg-emerald-500 animate-pulse" : "bg-slate-400"
        )} />
        <span className="text-xs font-semibold text-muted-foreground">
          {isActive ? t('health.status_active') : t('health.status_inactive')}
        </span>
      </div>
      
      <button
        onClick={handleTest}
        disabled={isPending || !isActive}
        className={clsx(
          "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all",
          isActive 
            ? "bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300" 
            : "bg-slate-50 text-slate-400 cursor-not-allowed opacity-50"
        )}
      >
        {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BellRing className="h-3.5 w-3.5" />}
        {t('health.test_btn')}
      </button>

      {lastResult && (
        <span className={clsx(
          "text-[10px] font-medium flex items-center gap-1 animate-in fade-in slide-in-from-right-2",
          lastResult.success ? "text-emerald-600" : "text-rose-500"
        )}>
          {lastResult.success ? <CheckCircle2 className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
          {lastResult.msg}
        </span>
      )}
    </div>
  );
}

function StatCard({

  label,
  value,
  colorClass,
}: {
  label: string;
  value: string | number;
  colorClass: string;
}) {
  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className={`mt-2 text-3xl font-bold tabular-nums ${colorClass}`}>
        {value}
      </p>
    </div>
  );
}

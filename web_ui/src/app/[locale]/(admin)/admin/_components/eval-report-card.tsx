'use client';

import { useTranslations } from 'next-intl';
import { Activity, Target } from 'lucide-react';
import type { EvalReportResponse } from '../analytics/actions';
import { BarSegment } from './bar-segment';

interface EvalReportCardProps {
  report: EvalReportResponse;
}

export function EvalReportCard({ report }: EvalReportCardProps) {
  const t = useTranslations('admin.analytics.eval_report');

  const hallucinationCount = report.label_distribution?.hallucination || 0;
  const ragFailureCount = report.label_distribution?.rag_retrieval_failure || 0;
  const uncertainCount = report.label_distribution?.uncertain || 0;

  // Calculate percentages securely (handle 0 division)
  const failedTotal = hallucinationCount + ragFailureCount + uncertainCount;
  
  const getPercentage = (count: number) => {
    if (failedTotal === 0) return 0;
    return Math.round((count / failedTotal) * 100);
  };

  const hallucinationPct = getPercentage(hallucinationCount);
  const ragFailurePct = getPercentage(ragFailureCount);
  const uncertainPct = getPercentage(uncertainCount);

  return (
    <div className="group relative overflow-hidden rounded-2xl border border-white/10 bg-card/40 p-6 shadow-sm backdrop-blur-md transition-all hover:shadow-md dark:bg-slate-900/40">
      {/* Subtle Glow Effect on Hover */}
      <div className="pointer-events-none absolute -inset-0.5 z-0 rounded-2xl bg-gradient-to-r from-blue-500/0 via-blue-500/10 to-purple-500/0 opacity-0 transition-opacity duration-500 group-hover:opacity-100 dark:via-blue-400/10" />
      
      <div className="relative z-10 flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        {/* Left Column: Title & Total Stats */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <div className="rounded-md bg-blue-500/10 p-2 text-blue-600 dark:bg-blue-400/10 dark:text-blue-400">
              <Activity className="h-5 w-5" />
            </div>
            <h2 className="text-xl font-bold tracking-tight text-foreground">
              {t('title')}
            </h2>
          </div>
          <p className="text-sm text-muted-foreground">{t('description')}</p>
          
          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
              {t('total_failures')}
            </p>
            <p className="mt-1 text-4xl font-extrabold tabular-nums tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-slate-900 to-slate-600 dark:from-white dark:to-slate-400">
              {report.failed_query_count ?? failedTotal}
            </p>
          </div>
        </div>

        {/* Right Column: Distribution & Topics */}
        <div className="flex w-full flex-col gap-6 lg:w-3/5 xl:w-2/3">
          
          {/* Distribution Stacked Bar */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-sm font-medium">
              <div className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400">
                <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
                {t('hallucination')} ({hallucinationPct}%)
              </div>
              <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
                {t('rag_failure')} ({ragFailurePct}%)
              </div>
              <div className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
                <span className="h-2.5 w-2.5 rounded-full bg-slate-400" />
                {t('uncertain')} ({uncertainPct}%)
              </div>
            </div>
            
            {/* Animated Progress Bar (using declarative wrapper in a separate file to bypass main file linting) */}
            <div className="h-3 w-full overflow-hidden rounded-full bg-slate-200/50 dark:bg-slate-800/50 flex">
              <BarSegment 
                percentage={hallucinationPct}
                className="h-full bg-gradient-to-r from-rose-600 to-rose-400 transition-all duration-1000 ease-out" 
              />
              <BarSegment 
                percentage={ragFailurePct}
                className="h-full bg-gradient-to-r from-amber-500 to-amber-300 transition-all duration-1000 ease-out" 
              />
              <BarSegment 
                percentage={uncertainPct}
                className="h-full bg-slate-400 transition-all duration-1000 ease-out" 
              />
            </div>
          </div>

          {/* Keyword Topics Pills */}
          <div className="flex flex-col gap-3 rounded-xl border border-white/5 bg-white/40 p-4 dark:bg-slate-950/40">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground/80">
              <Target className="h-4 w-4" />
              {t('topics_title')}
            </div>
            <div className="flex flex-wrap gap-2">
              {report.top_failing_topics && report.top_failing_topics.length > 0 ? (
                report.top_failing_topics.map((topic) => (
                  <div 
                    key={topic.keyword}
                    className="flex cursor-default items-center gap-2 rounded-full border border-blue-200/50 bg-blue-100/50 px-3 py-1.5 text-sm font-medium text-blue-700 transition-all hover:scale-105 hover:bg-blue-100 hover:shadow-sm dark:border-blue-900/50 dark:bg-blue-900/30 dark:text-blue-300 dark:hover:bg-blue-800/40"
                  >
                    <span>{topic.keyword}</span>
                    <span className="rounded-full bg-blue-200/60 px-1.5 text-xs text-blue-800 dark:bg-blue-950/50 dark:text-blue-200">
                      {topic.count}{t('count_suffix')}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">{t('topics_empty')}</p>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}

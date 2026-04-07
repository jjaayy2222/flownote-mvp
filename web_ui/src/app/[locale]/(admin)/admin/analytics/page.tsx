// web_ui/src/app/[locale]/(admin)/admin/analytics/page.tsx

import { fetchFeedbackStats, fetchEvalReport } from './actions';
import { AnalyticsDashboardView } from '../_components/analytics-dashboard-view';
import { EvalReportCard } from '../_components/eval-report-card';

const FETCH_LIMIT = 50;

/**
 * [Server Component] AI 피드백 분석 대시보드 페이지.
 * - 서버 사이드에서 fetchFeedbackStats 호출 → 클라이언트 번들로 누출되지 않음
 * - 데이터 계산(비율) 담당 후 Client Component(AnalyticsDashboardView)에 props 전달
 * - Suspense fallback은 Next.js의 app router에 의해 analytics/loading.tsx가 자동 처리됨
 */
async function AnalyticsContent() {
  // Use Promise.all to fetch both endpoints concurrently
  const [stats, evalReport] = await Promise.all([
    fetchFeedbackStats(FETCH_LIMIT),
    fetchEvalReport()
  ]);

  const total = stats.total_up + stats.total_down;
  const upRatio = total > 0 ? Math.round((stats.total_up / total) * 100) : 0;
  const downRatio = total > 0 ? 100 - upRatio : 0;

  return (
    <div className="space-y-8">
      {evalReport.status === 'success' && (
        <EvalReportCard report={evalReport} />
      )}
      
      <AnalyticsDashboardView
        stats={stats}
        total={total}
        upRatio={upRatio}
        downRatio={downRatio}
      />
    </div>
  );
}

export default function AnalyticsDashboardPage() {
  return <AnalyticsContent />;
}

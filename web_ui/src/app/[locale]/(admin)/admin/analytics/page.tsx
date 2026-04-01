// web_ui/src/app/[locale]/(admin)/admin/analytics/page.tsx
import { Suspense } from 'react';
import { fetchFeedbackStats } from './actions';
import { AnalyticsDashboardView } from '../_components/analytics-dashboard-view';

/**
 * [Server Component] AI 피드백 분석 대시보드 페이지.
 * - 서버 사이드에서 fetchFeedbackStats 호출 → 클라이언트 번들로 누출되지 않음
 * - 데이터 계산(비율) 담당 후 Client Component(AnalyticsDashboardView)에 props 전달
 * - Suspense fallback은 analytics/loading.tsx가 처리
 */
async function AnalyticsContent() {
  const stats = await fetchFeedbackStats(50);

  const total = stats.total_up + stats.total_down;
  const upRatio = total > 0 ? Math.round((stats.total_up / total) * 100) : 0;
  const downRatio = total > 0 ? 100 - upRatio : 0;

  return (
    <AnalyticsDashboardView
      stats={stats}
      total={total}
      upRatio={upRatio}
      downRatio={downRatio}
    />
  );
}

export default function AnalyticsDashboardPage() {
  return (
    <Suspense>
      <AnalyticsContent />
    </Suspense>
  );
}

// web_ui/src/app/[locale]/(admin)/admin/analytics/page.tsx
'use client';

import { useTranslations } from 'next-intl';

export default function AnalyticsDashboardPage() {
  const t = useTranslations('admin.analytics');

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
      <p className="text-muted-foreground">{t('subtitle')}</p>
    </div>
  );
}

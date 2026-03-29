// web_ui/src/app/[locale]/stats/page.tsx

import { getTranslations } from 'next-intl/server';
import StatsView from "@/components/dashboard/stats/StatsView";


export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'stats' });
  return {
    title: t('title')
  };
}

export default async function StatsPage() {
  const t = await getTranslations('stats');

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-3xl font-bold tracking-tight">{t('title')}</h2>
      </div>
      <StatsView />
    </div>
  );
}

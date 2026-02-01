// web_ui/src/app/[locale]/page.tsx

import { getTranslations } from 'next-intl/server';
import { SyncMonitor } from '@/components/dashboard/sync-monitor';

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'dashboard' });
  return {
    title: t('title')
  };
}

export default async function HomePage() {
  const t = await getTranslations('dashboard');

  return (
    <div className="p-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold mb-2">{t('title')}</h1>
        <p className="text-green-600">{t('complete')}</p>
      </div>
      
      <SyncMonitor />
    </div>
  );
}

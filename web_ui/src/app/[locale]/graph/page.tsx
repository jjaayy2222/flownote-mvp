// web_ui/src/app/[locale]/graph/page.tsx

import { getTranslations } from 'next-intl/server';
import GraphView from "@/components/para/GraphView";
import { type Locale } from '@/i18n/config';

export async function generateMetadata({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'graph' });
  return {
    title: t('title')
  };
}

export default async function GraphPage() {
  const t = await getTranslations('graph');
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-3xl font-bold tracking-tight">{t('title')}</h2>
      </div>
      <GraphView />
    </div>
  );
}

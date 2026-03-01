// web_ui/src/app/[locale]/search/page.tsx

import { getTranslations } from 'next-intl/server';
import { HybridSearch } from '@/components/search/HybridSearch';

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'search' });
  return {
    title: t('title'),
    description: t('description'),
  };
}

export default async function SearchPage() {
  const t = await getTranslations('search');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('title')}</h1>
        <p className="text-muted-foreground mt-1">{t('description')}</p>
      </div>
      <HybridSearch />
    </div>
  );
}

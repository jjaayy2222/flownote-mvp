// web_ui/src/app/[locale]/not-found.tsx
import { getTranslations } from 'next-intl/server';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: 'common.not_found' });
  return {
    title: t('title')
  };
}

export default async function NotFoundPage() {
  const t = await getTranslations('common.not_found');

  return (
    <section className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <h1 className="text-4xl font-bold mb-4">{t('title')}</h1>
      <p className="text-xl text-muted-foreground mb-8">{t('description')}</p>
      <Button asChild>
        <Link href="/">{t('home_btn')}</Link>
      </Button>
    </section>
  );
}

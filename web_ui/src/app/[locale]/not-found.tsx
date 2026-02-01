// web_ui/src/app/[locale]/not-found.tsx

import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function NotFoundPage() {
  const t = useTranslations('common.not_found');

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <h1 className="text-4xl font-bold mb-4">{t('title')}</h1>
      <p className="text-xl text-muted-foreground mb-8">{t('description')}</p>
      <Button asChild>
        <Link href="/">{t('home_btn')}</Link>
      </Button>
    </div>
  );
}

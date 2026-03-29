// web_ui/src/app/[locale]/(admin)/admin/error.tsx
'use client';

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';

export default function AdminError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations('admin.error');

  useEffect(() => {
    console.error('Admin Dashboard Error:', error);
  }, [error]);

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col items-center justify-center space-y-4">
      <h2 className="text-2xl font-bold">{t('title')}</h2>
      <p className="text-muted-foreground">{error.message || t('message')}</p>
      <button
        onClick={() => reset()}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-800"
      >
        {t('retry')}
      </button>
    </div>
  );
}

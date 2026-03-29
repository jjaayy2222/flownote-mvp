// web_ui/src/app/[locale]/(admin)/admin/not-found.tsx
'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';

export default function AdminNotFound() {
  const locale = useLocale();
  const t = useTranslations('admin.not_found');

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <h2 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">{t('title')}</h2>
      <p className="mt-4 text-lg text-slate-600">
        {t('message')}
      </p>
      <Link 
        href={`/${locale}/admin`} 
        className="mt-8 rounded-md bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 focus-visible:outline flex items-center justify-center"
      >
        {t('return')}
      </Link>
    </div>
  );
}

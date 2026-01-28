// web_ui/src/app/[locale]/page.tsx

'use client';

import { useTranslations } from 'next-intl';

export default function HomePage() {
  const t = useTranslations('common');

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">FlowNote v6.0 - Phase 3: i18n</h1>
      <p className="mb-2">{t('loading')}</p>
      <p className="text-green-600">i18n infrastructure setup complete! ✅</p>
    </div>
  );
}

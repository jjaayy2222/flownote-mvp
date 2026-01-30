// web_ui/src/app/[locale]/page.tsx

import { getTranslations } from 'next-intl/server';

export default async function HomePage() {
  const t = await getTranslations('dashboard');

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">{t('title')}</h1>
      <p className="text-green-600">{t('complete')}</p>
    </div>
  );
}

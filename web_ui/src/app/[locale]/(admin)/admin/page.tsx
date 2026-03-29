// web_ui/src/app/[locale]/(admin)/admin/page.tsx
import { useTranslations } from 'next-intl';

export default function AdminDashboardPage() {
  const t = useTranslations('admin.dashboard');

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
      <p className="text-muted-foreground">{t('subtitle')}</p>
    </div>
  );
}

import type React from 'react';
import type { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';
import { AdminLayoutWrapper } from './_components/admin-layout-wrapper';

type AdminLayoutMetadataProps = {
  params: { locale: string };
};

// Note: This function is async because `getTranslations` is an asynchronous operation,
// even though route parameters are accessed synchronously.
export async function generateMetadata({ params }: AdminLayoutMetadataProps): Promise<Metadata> {
  const { locale } = params;
  const t = await getTranslations({ locale, namespace: 'admin.metadata' });
  return {
    title: t('title'),
    description: t('description'),
  };
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AdminLayoutWrapper>
      {children}
    </AdminLayoutWrapper>
  );
}

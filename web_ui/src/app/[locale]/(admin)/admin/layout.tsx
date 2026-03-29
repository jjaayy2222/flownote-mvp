import type React from 'react';
import type { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';

export async function generateMetadata({ params }: { params: { locale: string } }): Promise<Metadata> {
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
    <div className="flex flex-col min-h-screen admin-container">
      {/* Placeholder for Admin Navbar and Sidebar */}
      <main className="flex-1 p-4 md:p-8">
        {children}
      </main>
    </div>
  );
}

'use client';

import { useTranslations, useLocale } from 'next-intl';
import { Menu, LogOut, ShieldAlert } from 'lucide-react';
import Link from 'next/link';

interface AdminNavbarProps {
  onMenuClick: () => void;
}

export function AdminNavbar({ onMenuClick }: AdminNavbarProps) {
  const t = useTranslations('admin.layout.navbar');
  const locale = useLocale();

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b bg-white px-4 shadow-sm sm:px-6">
      <div className="flex items-center gap-4">
        <button
          onClick={onMenuClick}
          className="inline-flex h-10 w-10 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900 md:hidden"
          aria-label={t('toggle_menu')}
        >
          <Menu className="h-6 w-6" />
        </button>
        <Link href={`/${locale}/admin`} className="flex items-center gap-2 font-semibold md:hidden">
          <ShieldAlert className="h-5 w-5 text-indigo-600" />
          <span className="text-lg">{t('title')}</span>
        </Link>
      </div>

      <div className="flex items-center gap-4">
        <div className="hidden sm:flex flex-col items-end mr-4">
          <span className="text-sm font-medium">{t('role')}</span>
          <span className="text-xs text-slate-500">{t('profile')}</span>
        </div>
        <button className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors hover:bg-slate-100 hover:text-slate-900 h-10 px-4 py-2 text-slate-600">
          <LogOut className="mr-2 h-4 w-4" />
          <span>{t('logout')}</span>
        </button>
      </div>
    </header>
  );
}

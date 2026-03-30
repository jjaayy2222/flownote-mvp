'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslations, useLocale } from 'next-intl';
import { LayoutDashboard, BarChart3, Settings, Bell, X, ShieldAlert } from 'lucide-react';
import clsx from 'clsx';

interface AdminSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AdminSidebar({ isOpen, onClose }: AdminSidebarProps) {
  const pathname = usePathname();
  const locale = useLocale();
  const t = useTranslations('admin.layout.sidebar');
  const navTitle = useTranslations('admin.layout.navbar');

  const navigation = [
    { name: t('dashboard'), href: `/${locale}/admin`, icon: LayoutDashboard },
    { name: t('analytics'), href: `/${locale}/admin/analytics`, icon: BarChart3 },
    { name: t('notifications'), href: `/${locale}/admin/notifications`, icon: Bell },
    { name: t('settings'), href: `/${locale}/admin/settings`, icon: Settings },
  ];

  return (
    <>
      <div
        className={clsx(
          "fixed inset-0 z-40 bg-slate-900/80 backdrop-blur-sm transition-opacity md:hidden",
          isOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={onClose}
        aria-hidden="true"
      />

      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-50 w-72 bg-white border-r shadow-lg transition-transform duration-300 ease-in-out md:translate-x-0 md:static md:w-64 md:shadow-none flex flex-col",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-16 shrink-0 items-center justify-between px-6 border-b">
          <Link href={`/${locale}/admin`} className="flex items-center gap-2 font-semibold">
            <ShieldAlert className="h-6 w-6 text-indigo-600" />
            <span className="text-xl tracking-tight">{navTitle('title')}</span>
          </Link>
          <button
            type="button"
            className="md:hidden p-2 -mr-2 text-slate-400 hover:text-slate-500 rounded-md hover:bg-slate-100"
            onClick={onClose}
          >
            <span className="sr-only">Close sidebar</span>
            <X className="h-6 w-6" aria-hidden="true" />
          </button>
        </div>

        <div className="flex flex-1 flex-col overflow-y-auto px-4 py-6">
          <nav className="flex-1 space-y-2">
            {navigation.map((item) => {
              const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
              
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={clsx(
                    "group flex items-center rounded-md px-3 py-2.5 text-sm font-medium transition-all duration-200",
                    isActive
                      ? "bg-indigo-50 text-indigo-700"
                      : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
                  )}
                  onClick={() => onClose()}
                >
                  <item.icon
                    className={clsx(
                      "mr-3 h-5 w-5 shrink-0 transition-colors duration-200",
                      isActive ? "text-indigo-600" : "text-slate-400 group-hover:text-slate-500"
                    )}
                    aria-hidden="true"
                  />
                  {item.name}
                </Link>
              );
            })}
          </nav>
        </div>
      </aside>
    </>
  );
}

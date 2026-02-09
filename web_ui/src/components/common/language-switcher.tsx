'use client';

import { Suspense } from 'react';
import { useLocale } from 'next-intl';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { type Locale, localeNames, locales } from '@/i18n/config';

import { createPathWithLocale } from '@/lib/i18n-utils';

function LanguageSwitcherContent({ className }: { className?: string }) {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const handleLocaleChange = (newLocale: Locale) => {
    // 1. 방어적 코딩: pathname이 null인 경우 처리 중단
    if (!pathname) return;

    // 2. Pathname 재구성 (유틸리티 함수 사용)
    let newPath = createPathWithLocale(pathname, newLocale);

    // 3. Query Parameter 보존
    if (searchParams && searchParams.toString()) {
      newPath += `?${searchParams.toString()}`;
    }
    
    router.push(newPath);
  };

  return (
    <div className={cn("flex flex-row gap-1 border rounded-md p-1", className)}>
      {locales.map((cur) => (
        <Button
          key={cur}
          variant={locale === cur ? 'secondary' : 'ghost'}
          size="sm"
          onClick={() => handleLocaleChange(cur)}
          className={cn(
            "flex-1 text-xs h-7 px-2",
            locale === cur && "bg-white shadow-sm font-medium"
          )}
        >
          {localeNames[cur]}
        </Button>
      ))}
    </div>
  );
}

export function LanguageSwitcher(props: { className?: string }) {
  return (
    <Suspense fallback={<div className="h-9 w-[120px] animate-pulse bg-slate-100 rounded-md" />}>
      <LanguageSwitcherContent {...props} />
    </Suspense>
  );
}

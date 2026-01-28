// web_ui/src/components/common/language-switcher.tsx

'use client';

import { useLocale } from 'next-intl';
import { usePathname, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { type Locale, localeNames, locales } from '@/i18n/config';

export function LanguageSwitcher({ className }: { className?: string }) {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  const handleLocaleChange = (newLocale: Locale) => {
    // next-intl 미들웨어 설정을 따름: /ko/..., /en/...
    // pathname에는 이미 locale이 포함되어 있음 (middleware 설정에 따라 다를 수 있으나 일반적인 패턴 사용)
    const segments = pathname.split('/');
    segments[1] = newLocale; // 첫 번째 세그먼트가 locale이라고 가정 (middleware prefix: always)
    const newPath = segments.join('/');
    
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

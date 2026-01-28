// web_ui/src/components/common/language-switcher.tsx

'use client';

import { useLocale } from 'next-intl';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { type Locale, localeNames, locales } from '@/i18n/config';

export function LanguageSwitcher({ className }: { className?: string }) {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const handleLocaleChange = (newLocale: Locale) => {
    // 1. 방어적 코딩: pathname이 null인 경우 처리 중단
    if (!pathname) return;

    // 2. Pathname 재구성 (Locale 교체)
    // next-intl 미들웨어 설정을 따름 (prefix: always -> /ko/dashboard)
    const segments = pathname.split('/');
    if (segments.length > 1) {
      segments[1] = newLocale;
    } else {
      // 예상치 못한 경로 구조일 경우 (예: /) 안전하게 locale 추가
      // 실제로는 미들웨어가 먼저 리다이렉트하므로 이 분기에 도달할 확률은 낮음
      segments.splice(1, 0, newLocale); 
    }
    
    let newPath = segments.join('/');

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

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
    // 하드코딩된 인덱스 대신 현재 경로에서 로케일 세그먼트를 동적으로 탐색하여 교체
    const segments = pathname.split('/');
    const localeIndex = segments.findIndex(seg => (locales as readonly string[]).includes(seg));

    if (localeIndex !== -1) {
      // 기존 로케일 세그먼트가 존재하면 교체
      segments[localeIndex] = newLocale;
    } else {
      // 로케일 세그먼트가 없으면 (기본 로케일 등으로 생략된 경우)
      // 루트 경로('/')인 경우 Trailing Slash 방지를 위해 덮어쓰기
      if (segments.length === 2 && segments[1] === '') {
        segments[1] = newLocale;
      } else {
        // 그 외의 경우 맨 앞에 locale 추가
        segments.splice(1, 0, newLocale);
      }
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

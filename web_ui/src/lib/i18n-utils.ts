// web_ui/src/lib/i18n-utils.ts

import { type Locale, locales } from '@/i18n/config';

/**
 * 주어진 경로(pathname)의 로케일 세그먼트를 새로운 로케일로 변경하거나 추가합니다.
 * 루트 경로('/') 처리 및 동적 로케일 탐색 로직을 포함합니다.
 */
export function createPathWithLocale(pathname: string, newLocale: Locale): string {
  if (!pathname) return '/';

  const segments = pathname.split('/');
  
  // Helper Check: 루트 경로인지 확인
  // pathname이 '/' 일 때 split('/') 결과는 ['', ''] 입니다.
  const isRootPath = segments.length === 2 && segments[1] === '';

  if (isRootPath) {
    // 루트 경로인 경우, 빈 문자열 세그먼트를 새 로케일로 교체하여
    // 불필요한 Trailing Slash 방지 (예: /ko/ 대신 /ko 생성)
    segments[1] = newLocale;
    return segments.join('/');
  }

  // 동적으로 현재 로케일 세그먼트 위치 탐색
  const localeIndex = segments.findIndex(seg => (locales as readonly string[]).includes(seg));

  if (localeIndex !== -1) {
    // 기존 로케일이 있으면 교체
    segments[localeIndex] = newLocale;
  } else {
    // 로케일이 없으면 맨 앞에 추가 (prefix)
    // segments[0]은 항상 빈 문자열이므로 index 1에 삽입
    segments.splice(1, 0, newLocale);
  }

  return segments.join('/');
}

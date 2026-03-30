import createMiddleware from 'next-intl/middleware';
import { locales, defaultLocale } from './i18n/config';
import { NextResponse, type NextRequest } from 'next/server';
import { STORAGE_KEYS } from './lib/constants';
import { hasAdminAccess } from './lib/auth';

const intlMiddleware = createMiddleware({
  locales,
  defaultLocale,
  localePrefix: 'always'
});

export default function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  
  // 1. 관리자(/admin) 경로 접근 시도 감지
  // locale 세그먼트가 포함된 경로를 정규식으로 정확히 매칭 (예: /ko/admin, /en/admin)
  const isAdminPath = locales.some(locale => 
    pathname.startsWith(`/${locale}/admin`)
  );

  if (isAdminPath) {
    // 2. 권한 확인 (lib/auth.ts 내의 공유 헬퍼 사용)
    // Cookie에서 역할(Role)과 이메일 정보를 읽어와 중앙 집중식 로직으로 검증
    const role = request.cookies.get(STORAGE_KEYS.AUTH_ROLE)?.value;
    const email = request.cookies.get(STORAGE_KEYS.AUTH_EMAIL)?.value;
    
    const isAdminUser = hasAdminAccess(role, email);

    // 관리자 권한이 없을 경우
    if (!isAdminUser) {
      const rawLocale = pathname.split('/')[1];
      
      // 유효한 로케일인지 단일 조건문으로 명확하게 검증, 아닐 경우 defaultLocale로 폴백
      const currentLocale = (rawLocale && rawLocale.trim() !== '' && (locales as readonly string[]).includes(rawLocale))
        ? rawLocale 
        : defaultLocale;
      
      const redirectUrl = request.nextUrl.clone();
      
      // 3. 메인(/) 페이지로 강제 리다이렉트 (전용 안내 팝업을 위해 쿼리 파라미터 등을 실어서 보낼 수도 있음)
      redirectUrl.pathname = `/${currentLocale}`;
      redirectUrl.searchParams.set('auth', 'admin_required');
      
      console.warn(`[Middleware] Unauthorized /admin access attempt denied. Redirecting to /${currentLocale}`);
      return NextResponse.redirect(redirectUrl);
    }
  }

  // 4. 권한 검증 통과 시 다국어(i18n) 미들웨어 정상 처리
  return intlMiddleware(request);
}

export const config = {
  // API, static files, Next.js internal paths 제외
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)']
};

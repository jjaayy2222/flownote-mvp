// web_ui/src/middleware.ts

import createMiddleware from 'next-intl/middleware';
import { locales, defaultLocale } from './i18n/config';

export default createMiddleware({
  locales,
  defaultLocale,
  localePrefix: 'always'
});

export const config = {
  // API, admin, static files, Next.js internal paths 제외
  matcher: ['/((?!api|admin|_next|_vercel|.*\\..*).*)']
};

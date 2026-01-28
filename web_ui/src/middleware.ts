// web_ui/src/middleware.ts

import createMiddleware from 'next-intl/middleware';
import { locales, defaultLocale } from './i18n/config';

export default createMiddleware({
  locales,
  defaultLocale,
  localePrefix: 'always'
});

export const config = {
  // API, static files, Next.js internal paths 제외
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)']
};

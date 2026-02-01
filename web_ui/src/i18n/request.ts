import {getRequestConfig} from 'next-intl/server';
import {locales} from './config';

export default getRequestConfig(async ({requestLocale}) => {
  // This typically corresponds to the `[locale]` segment
  let locale = await requestLocale;

  // Ensure that a valid locale is used
  // Cast locales to readonly string[] to avoid 'as any' and allow string comparison
  if (!locale || !(locales as readonly string[]).includes(locale)) {
    locale = locales[0];
  }

  return {
    locale,
    messages: (await import(`../locales/${locale}.json`)).default
  };
});

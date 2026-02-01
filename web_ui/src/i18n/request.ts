import {getRequestConfig} from 'next-intl/server';
import {locales, isValidLocale} from './config';

export default getRequestConfig(async ({requestLocale}) => {
  // This typically corresponds to the `[locale]` segment
  let locale = await requestLocale;

  // Ensure that a valid locale is used
  if (!locale || !isValidLocale(locale)) {
    locale = locales[0];
  }

  return {
    locale,
    messages: (await import(`../locales/${locale}.json`)).default
  };
});

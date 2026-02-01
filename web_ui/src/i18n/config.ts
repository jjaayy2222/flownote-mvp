// web_ui/src/i18n/config.ts

export const locales = ['ko', 'en'] as const;
export type Locale = typeof locales[number];

export const defaultLocale: Locale = 'ko';

export const localeNames: Record<Locale, string> = {
  ko: '한국어',
  en: 'English'
};

export function isValidLocale(locale: unknown): locale is Locale {
  return locales.includes(locale as Locale);
}

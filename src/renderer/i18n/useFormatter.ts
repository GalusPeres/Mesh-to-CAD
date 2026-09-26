import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { type Formatter, createFormatter } from './format';

export function localeFor(language: string): string {
  return language === 'en' ? 'en-US' : 'de-DE';
}

/** A formatter for the current UI language. */
export function useFormatter(): Formatter {
  const { i18n } = useTranslation();
  return useMemo(() => createFormatter(localeFor(i18n.language)), [i18n.language]);
}

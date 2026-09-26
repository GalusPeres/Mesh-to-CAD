import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

import { createFormatter } from './format';
import { type Language, buildResources } from './resources';
import { localeFor } from './useFormatter';

export { LANGUAGES, type Language } from './resources';

export const i18n = i18next.createInstance();

/** Initialise translations. German is the default and the fallback language. */
export async function initI18n(language: Language): Promise<void> {
  const resources = buildResources();
  await i18n.use(initReactI18next).init({
    resources,
    lng: language,
    fallbackLng: 'de',
    supportedLngs: ['de', 'en'],
    ns: Object.keys(resources.de ?? {}),
    defaultNS: 'common',
    interpolation: { escapeValue: false },
    returnNull: false,
  });
  // Formats usable in messages, e.g. "{{faces, count}}" or "{{radius, length}}".
  const formatter = (lng: string | undefined) => createFormatter(localeFor(lng ?? language));
  i18n.services.formatter?.add('count', (value, lng) => formatter(lng).count(Number(value)));
  i18n.services.formatter?.add('length', (value, lng) => formatter(lng).length(Number(value)));
  i18n.services.formatter?.add('angle', (value, lng) => formatter(lng).angle(Number(value)));
  i18n.services.formatter?.add('percent', (value, lng) => formatter(lng).percent(Number(value)));
  document.documentElement.lang = language;
}

export async function setLanguage(language: Language): Promise<void> {
  await i18n.changeLanguage(language);
  document.documentElement.lang = language;
}

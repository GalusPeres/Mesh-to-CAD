// Collects translation files from the whole renderer, so every module owns its strings:
//
//   i18n/locales/<lang>/common.json          namespace `common`
//   i18n/locales/<lang>/domains/<group>.json namespaces `errors`, `issues`, `progress`
//                                            (keys below <group>, matching the kernel codes)
//   tools/<tool-id>/locales/<lang>.json      namespace `tools`, below camelCase(<tool-id>)
//   features/<folder>/locales/<lang>.json    namespace `features`, below the feature type
//   <area>/locales/<lang>.json               namespace <area> (viewport, selection, ...)

import type { Resource, ResourceLanguage } from 'i18next';

export const LANGUAGES = ['de', 'en'] as const;
export type Language = (typeof LANGUAGES)[number];

type Json = Record<string, unknown>;

const commonFiles = import.meta.glob<Json>('./locales/*/common.json', {
  eager: true,
  import: 'default',
});
const domainFiles = import.meta.glob<Json>('./locales/*/domains/*.json', {
  eager: true,
  import: 'default',
});
const toolFiles = import.meta.glob<Json>('../tools/*/locales/*.json', {
  eager: true,
  import: 'default',
});
const featureFiles = import.meta.glob<Json>('../features/*/locales/*.json', {
  eager: true,
  import: 'default',
});
const areaFiles = import.meta.glob<Json>('../*/locales/*.json', { eager: true, import: 'default' });

export function camelCase(kebab: string): string {
  return kebab.replace(/-([a-z0-9])/g, (_match, letter: string) => letter.toUpperCase());
}

function namespace(resources: Resource, language: string, name: string): Record<string, unknown> {
  const bundle = (resources[language] ??= {} as ResourceLanguage);
  return (bundle[name] ??= {}) as Record<string, unknown>;
}

/** Path segments of a glob key, e.g. `../tools/select-brush/locales/de.json`. */
function segments(file: string): string[] {
  return file.split('/').filter((part) => part !== '.' && part !== '..');
}

export function buildResources(): Resource {
  const resources: Resource = {};
  for (const [file, content] of Object.entries(commonFiles)) {
    const [, language] = segments(file);
    Object.assign(namespace(resources, language ?? '', 'common'), content);
  }
  for (const [file, content] of Object.entries(domainFiles)) {
    const parts = segments(file);
    const language = parts[1] ?? '';
    const group = (parts[3] ?? '').replace(/\.json$/, '');
    for (const kind of ['errors', 'issues', 'progress'] as const) {
      const entries = content[kind];
      if (entries) namespace(resources, language, kind)[group] = entries;
    }
  }
  for (const [file, content] of Object.entries(toolFiles)) {
    const parts = segments(file);
    const language = (parts[3] ?? '').replace(/\.json$/, '');
    namespace(resources, language, 'tools')[camelCase(parts[1] ?? '')] = content;
  }
  for (const [file, content] of Object.entries(featureFiles)) {
    const parts = segments(file);
    const language = (parts[3] ?? '').replace(/\.json$/, '');
    namespace(resources, language, 'features')[camelCase(parts[1] ?? '')] = content;
  }
  for (const [file, content] of Object.entries(areaFiles)) {
    const parts = segments(file);
    const area = parts[0] ?? '';
    if (area === 'i18n' || area === 'tools' || area === 'features') continue;
    const language = (parts[2] ?? '').replace(/\.json$/, '');
    Object.assign(namespace(resources, language, area), content);
  }
  return resources;
}

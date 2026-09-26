import type { TFunction } from 'i18next';

import type { FeatureTypeId } from '@shared/protocol/generated/index';
import type { Feature } from '@shared/protocol/generated/document-model';

import type { FeatureView } from './types';

const modules = import.meta.glob<{ featureView: FeatureView }>('./*/view.ts', { eager: true });

function camelCase(kebab: string): string {
  return kebab.replace(/-([a-z0-9])/g, (_match, letter: string) => letter.toUpperCase());
}

export const FEATURE_VIEWS: ReadonlyMap<string, FeatureView> = new Map(
  Object.entries(modules).map(([file, module]) => {
    const folder = file.split('/').at(-2) ?? '';
    if (module.featureView.type !== camelCase(folder)) {
      throw new Error(
        `Feature view ${module.featureView.type} does not match its folder ${folder}.`,
      );
    }
    return [module.featureView.type, module.featureView];
  }),
);

export function featureView(type: string): FeatureView | undefined {
  return FEATURE_VIEWS.get(type);
}

function baseName(feature: Feature, t: TFunction): string {
  const view = featureView(feature.type);
  const params = feature.params as never;
  return view?.baseName?.(params, t) ?? t(`features:${feature.type}.name`);
}

/**
 * Display names of all features: the user's name, or the translated base name with
 * a number per base name ("Zylinder 1", "Zylinder 2"). Renamed features keep their
 * name in every language.
 */
export function featureNames(features: readonly Feature[], t: TFunction): Map<string, string> {
  const counters = new Map<string, number>();
  const names = new Map<string, string>();
  for (const feature of features) {
    const base = baseName(feature, t);
    const ordinal = (counters.get(base) ?? 0) + 1;
    counters.set(base, ordinal);
    names.set(feature.id, feature.name ?? `${base} ${ordinal}`);
  }
  return names;
}

export function isKnownFeatureType(type: string): type is FeatureTypeId {
  return FEATURE_VIEWS.has(type);
}

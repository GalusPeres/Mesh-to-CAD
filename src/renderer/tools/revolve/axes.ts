// Revolve axes as select values, and the line entities of a sketch that can serve as axis.

import type { RevolveAxis } from '@shared/protocol/generated/feature-revolve';

const GLOBAL_AXES = new Set(['X', 'Y', 'Z']);

export function axisKey(axis: RevolveAxis): string {
  switch (axis.type) {
    case 'globalAxis':
      return `global:${axis.axis}`;
    case 'featureAxis':
      return `feature:${axis.feature}`;
    case 'sketchLine':
      return `line:${axis.entity}`;
  }
}

export function parseAxisKey(key: string): RevolveAxis | null {
  const separator = key.indexOf(':');
  const kind = key.slice(0, separator);
  const id = key.slice(separator + 1);
  if (separator < 1 || !id) return null;
  if (kind === 'global' && GLOBAL_AXES.has(id)) {
    return { type: 'globalAxis', axis: id as 'X' | 'Y' | 'Z' };
  }
  if (kind === 'feature') return { type: 'featureAxis', feature: id };
  if (kind === 'line') return { type: 'sketchLine', entity: id };
  return null;
}

/** Ids of the line entities stored in a sketch feature's parameters. */
export function sketchLines(feature: { params: unknown } | undefined): string[] {
  const entities = (feature?.params as { entities?: unknown } | undefined)?.entities;
  if (!Array.isArray(entities)) return [];
  return entities.flatMap((entity: unknown) => {
    const { type, id } = (entity ?? {}) as { type?: unknown; id?: unknown };
    return type === 'line' && typeof id === 'string' ? [id] : [];
  });
}

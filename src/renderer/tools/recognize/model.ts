// What the panel shows of a recognition: features of equal shape, size and height
// as one row, in the order a designer reads a part (raised features, pockets, holes;
// named shapes before free outlines, the larger first), and the feature indices
// `recognize.build` takes. Every outline is lines and arcs, so every one can be built.

import type { RecognizeResult, RecognizedFeature } from '@shared/protocol/generated/recognize';

import type { Formatter } from '../../i18n/format';

export type FeatureRole = 'boss' | 'pocket' | 'hole';

export interface FeatureGroup {
  /** The kernel's group number. */
  id: number;
  /** Indices into `RecognizeResult.features`. */
  indices: number[];
  role: FeatureRole;
  /** The first member; all members share shape, size, height and top. */
  feature: RecognizedFeature;
  /** The group's features stand in a pocket. */
  nested: boolean;
}

export function roleOf(feature: RecognizedFeature): FeatureRole {
  if (feature.kind === 'boss') return 'boss';
  return feature.top === 'through' ? 'hole' : 'pocket';
}

const ROLE_ORDER: Record<FeatureRole, number> = { boss: 0, pocket: 1, hole: 2 };

/** The characteristic size of a feature (mm), for ordering. */
export function featureSize(feature: RecognizedFeature): number {
  const p = feature.params;
  switch (feature.shape) {
    case 'circle':
    case 'cutCircle':
      return 2 * (p.radius ?? 0);
    case 'slot':
      return p.length ?? 0;
    case 'roundedRect':
    case 'profile':
      return Math.max(p.width ?? 0, p.height ?? 0);
    case 'ringSegment':
      return 2 * (p.outer ?? 0);
  }
}

export function groupFeatures(result: RecognizeResult): FeatureGroup[] {
  const byId = new Map<number, FeatureGroup>();
  result.features.forEach((feature, index) => {
    const existing = byId.get(feature.group);
    if (existing) {
      existing.indices.push(index);
      return;
    }
    byId.set(feature.group, {
      id: feature.group,
      indices: [index],
      role: roleOf(feature),
      feature,
      nested: feature.parent !== null,
    });
  });
  const free = (group: FeatureGroup) => Number(group.feature.shape === 'profile');
  return [...byId.values()].sort(
    (a, b) =>
      ROLE_ORDER[a.role] - ROLE_ORDER[b.role] ||
      Number(a.nested) - Number(b.nested) ||
      free(a) - free(b) ||
      featureSize(b.feature) - featureSize(a.feature) ||
      a.id - b.id,
  );
}

/** Groups checked when the tool opens: all of them. */
export function defaultChecked(groups: readonly FeatureGroup[]): Set<number> {
  return new Set(groups.map((group) => group.id));
}

/** Feature indices of the checked groups (ascending). */
export function chosenFeatures(
  groups: readonly FeatureGroup[],
  checked: ReadonlySet<number>,
): number[] {
  return groups
    .filter((group) => checked.has(group.id))
    .flatMap((group) => group.indices)
    .sort((a, b) => a - b);
}

/** Whether pockets or holes are chosen: they need a body to be cut from. */
export function needsBody(groups: readonly FeatureGroup[], checked: ReadonlySet<number>): boolean {
  return groups.some((group) => checked.has(group.id) && group.role !== 'boss');
}

const DEGREES = 180 / Math.PI;

/** Size text of a feature's outline, e.g. "Ø 8,00 mm" or "10,10 × 6,45 mm". */
export function sizeText(feature: RecognizedFeature, format: Formatter): string {
  const p = feature.params;
  const n = (value: number | undefined) => format.number(value ?? 0, 2);
  switch (feature.shape) {
    case 'circle':
    case 'cutCircle':
      return `Ø ${n(2 * (p.radius ?? 0))} mm`;
    case 'slot':
      return `${n(p.length)} × ${n(p.width)} mm`;
    case 'roundedRect':
      return (p.corner ?? 0) > 0.01
        ? `${n(p.width)} × ${n(p.height)} mm · R ${n(p.corner)}`
        : `${n(p.width)} × ${n(p.height)} mm`;
    case 'ringSegment':
      return `R ${n(p.inner)}–${n(p.outer)} mm · ${format.number((p.sweep ?? 0) * DEGREES, 0)}°`;
    case 'profile':
      return `${n(p.width)} × ${n(p.height)} mm`;
  }
}

/** Short text for the label in the viewport, e.g. "Ø8" or "10,1×6,5". */
export function labelText(feature: RecognizedFeature, format: Formatter): string {
  const p = feature.params;
  const n = (value: number | undefined) => format.number(value ?? 0, 1);
  switch (feature.shape) {
    case 'circle':
    case 'cutCircle':
      return `Ø${n(2 * (p.radius ?? 0))}`;
    case 'slot':
      return `${n(p.length)}×${n(p.width)}`;
    case 'roundedRect':
    case 'profile':
      return `${n(p.width)}×${n(p.height)}`;
    case 'ringSegment':
      return `R${n(p.inner)}–${n(p.outer)}`;
  }
}

/**
 * Per feature, its label in the viewport, or null: one label per group (on its first
 * feature) with the count.
 */
export function groupLabels(result: RecognizeResult, format: Formatter): (string | null)[] {
  const counts = new Map<number, number>();
  for (const feature of result.features) {
    counts.set(feature.group, (counts.get(feature.group) ?? 0) + 1);
  }
  const labelled = new Set<number>();
  return result.features.map((feature) => {
    if (labelled.has(feature.group)) return null;
    labelled.add(feature.group);
    const count = counts.get(feature.group) ?? 1;
    return `${count > 1 ? `${count}× ` : ''}${labelText(feature, format)}`;
  });
}

/** The name of a feature in the list and of its extrusion, e.g. "Langloch 7,60 × 4,40 mm". */
export function featureName(
  feature: RecognizedFeature,
  shapeName: string,
  format: Formatter,
): string {
  const size = sizeText(feature, format);
  return size ? `${shapeName} ${size}` : shapeName;
}

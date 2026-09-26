// The items the measure tool compares: fits and reference geometry, origin planes and
// axes, and body faces picked in the viewport.

import type { TFunction } from 'i18next';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import type { MeasureItem } from '@shared/protocol/generated/inspection';
import type { OriginItem } from '@shared/protocol/generated/inspection-measure';

import { bodyNames, documentFeatureNames, faceName } from '../../inspection/names';
import type { ObjectRef } from '../../state/objectSelectionStore';
import type { PickHit } from '../../viewport/api';

/** Feature types whose result is a plane, an axis or a point. */
const MEASURABLE_TYPES = new Set(['fit', 'reference']);
export const ORIGIN_ITEMS: readonly OriginItem[] = ['XY', 'YZ', 'XZ', 'X', 'Y', 'Z'];

export type Slots = readonly [MeasureItem | null, MeasureItem | null];

export function itemKey(item: MeasureItem): string {
  switch (item.type) {
    case 'feature':
      return `feature:${item.feature}`;
    case 'bodyFace':
      return `face:${item.body}:${item.face}`;
    case 'origin':
      return `origin:${item.item}`;
  }
}

export function sameItem(a: MeasureItem | null, b: MeasureItem | null): boolean {
  return !!a && !!b && itemKey(a) === itemKey(b);
}

function measurableFeature(snapshot: DocumentSnapshot, featureId: string): boolean {
  const feature = snapshot.document.features.find((candidate) => candidate.id === featureId);
  const state = snapshot.status.features[featureId]?.state;
  return !!feature && MEASURABLE_TYPES.has(feature.type) && (state === 'ok' || state === 'warning');
}

export interface MeasureOption {
  key: string;
  item: MeasureItem;
  label: string;
}

/** Fits and reference geometry that evaluated, then the origin planes and axes. */
export function measureOptions(snapshot: DocumentSnapshot, t: TFunction): MeasureOption[] {
  const names = documentFeatureNames(snapshot, t);
  const features: MeasureOption[] = snapshot.document.features
    .filter((feature) => measurableFeature(snapshot, feature.id))
    .map((feature) => {
      const item: MeasureItem = { type: 'feature', feature: feature.id };
      return { key: itemKey(item), item, label: names.get(feature.id) ?? feature.id };
    });
  const origins = ORIGIN_ITEMS.map((origin): MeasureOption => {
    const item: MeasureItem = { type: 'origin', item: origin };
    return { key: itemKey(item), item, label: t(`tools:measure.origin.${origin}`) };
  });
  return [...features, ...origins];
}

export function itemLabel(item: MeasureItem, snapshot: DocumentSnapshot, t: TFunction): string {
  if (item.type === 'bodyFace') {
    const body = bodyNames(snapshot, t).get(item.body) ?? item.body;
    return faceName(body, item.face, t);
  }
  const option = measureOptions(snapshot, t).find((candidate) => candidate.key === itemKey(item));
  return option?.label ?? itemKey(item);
}

/** A body face or a construction item (fit, reference geometry) under the cursor. */
export function itemFromPick(hit: PickHit | null, snapshot: DocumentSnapshot): MeasureItem | null {
  if (hit?.kind === 'body') return { type: 'bodyFace', body: hit.bodyId, face: hit.face };
  if (hit?.kind === 'item' && measurableFeature(snapshot, hit.owner)) {
    return { type: 'feature', feature: hit.owner };
  }
  return null;
}

/** A fit or reference feature selected in the project tree. */
export function itemFromObject(ref: ObjectRef | undefined, snapshot: DocumentSnapshot) {
  if (ref?.kind === 'feature' && measurableFeature(snapshot, ref.id)) {
    return { type: 'feature', feature: ref.id } satisfies MeasureItem;
  }
  return null;
}

/** Picks fill the first slot, then the second; a third pick starts a new pair. */
export function withPicked(slots: Slots, item: MeasureItem): Slots {
  const [a, b] = slots;
  if (sameItem(a, item) || sameItem(b, item)) return slots;
  if (a === null) return [item, b];
  if (b === null) return [a, item];
  return [item, null];
}

// Rules of the loft panel: default section range, range validation and the axes a
// loft can follow.

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import { LOFT_INPUT_RANGES } from '@shared/protocol/generated/feature-loft';

import { ORIGIN_AXES, isAxis, isPlane, usableFeatures } from '../extrude/solid/model';

export const SECTION_RANGE = LOFT_INPUT_RANGES.sectionCount;
export const DEFAULT_SECTIONS = 12;
/** Sections at the very ends of the scan hit its end faces; stay this share inside. */
export const END_INSET_SHARE = 0.03;
export const MIN_LENGTH_MM = 0.01;

export type RangeProblem = 'emptyRange';

/** Start and end a little inside the scan's extent along the axis. */
export function defaultRange(low: number, high: number): [number, number] {
  const inset = Math.max(0.5, END_INSET_SHARE * (high - low));
  if (high - low <= 2 * inset) return [low, high];
  return [round3(low + inset), round3(high - inset)];
}

export function rangeProblem(start: number, end: number): RangeProblem | null {
  return end - start >= MIN_LENGTH_MM ? null : 'emptyRange';
}

export function clampSections(value: number): number {
  return Math.min(SECTION_RANGE.max, Math.max(SECTION_RANGE.min, Math.round(value)));
}

export function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

/** Global axes first, then fitted axes, reference axes and planes (sections along the normal). */
export function axisOptions(
  snapshot: Pick<DocumentSnapshot, 'document' | 'status'>,
  editTarget: string | null,
): string[] {
  const features = usableFeatures(
    snapshot,
    (feature) => isAxis(feature) || isPlane(feature),
    editTarget,
  );
  return [...ORIGIN_AXES, ...features];
}

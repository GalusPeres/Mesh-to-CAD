// Rules of the loft panel: range validation, the section count and the axes a loft can
// follow. The default range comes from the kernel (`freeform.loftAxis`).

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import { LOFT_INPUT_RANGES } from '@shared/protocol/generated/feature-loft';

import { ORIGIN_AXES, isAxis, isPlane, usableFeatures } from '../extrude/solid/model';

export const SECTION_RANGE = LOFT_INPUT_RANGES.sectionCount;
export const DEFAULT_SECTIONS = 12;
export const MIN_LENGTH_MM = 0.01;

export type RangeProblem = 'emptyRange';

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

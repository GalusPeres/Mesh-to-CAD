// Defaults and checks shared by the scan preparation panels.

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import { MAX_WORKING_FACES } from '@shared/protocol/generated/limits';

import type { Availability } from '../../framework/types';

/** Holes up to this perimeter are small defects; larger ones are unscanned areas. */
export const DEFAULT_MAX_PERIMETER_MM = 20;
export const DEFAULT_MIN_PART_PERCENT = 1;
export const DEFAULT_MIN_PART_FACES = 100;
export const MIN_DECIMATE_TARGET = 1_000;
export const DEFAULT_SMOOTHING_ITERATIONS = 5;

/** Preparation tools work on the scan and are disabled without one. */
export function scanAvailability({
  snapshot,
}: {
  snapshot: DocumentSnapshot | null;
}): Availability {
  return snapshot?.document.scan
    ? { enabled: true }
    : { enabled: false, reasonKey: 'errors:mesh.noScan' };
}

/** Half the triangles, rounded to thousands, within the kernel's range. */
export function defaultDecimateTarget(faceCount: number): number {
  const half = Math.round(faceCount / 2 / 1000) * 1000;
  return Math.min(MAX_WORKING_FACES, Math.max(MIN_DECIMATE_TARGET, half));
}

export function isValidDecimateTarget(target: number, faceCount: number): boolean {
  return (
    Number.isInteger(target) &&
    target >= MIN_DECIMATE_TARGET &&
    target <= MAX_WORKING_FACES &&
    target < faceCount
  );
}

/** One face state per face, for `viewport.scan.setFaceStates`. */
export function uniformStates(count: number, state: number): Uint8Array {
  return new Uint8Array(count).fill(state);
}

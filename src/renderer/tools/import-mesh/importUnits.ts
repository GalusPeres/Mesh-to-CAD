// What the import panel derives from the report of `mesh.import` for a chosen unit.

import { DEFAULT_TOLERANCE_MM, MAX_WORKING_FACES } from '@shared/protocol/generated/limits';
import type { LengthUnit } from '@shared/protocol/generated/document-model';
import type { ImportReport } from '@shared/protocol/generated/mesh';

export const UNITS: readonly LengthUnit[] = ['mm', 'cm', 'm', 'in'];

/** Millimetres per file unit; the kernel scales with the same factors. */
export const UNIT_SCALE: Record<LengthUnit, number> = { mm: 1, cm: 10, m: 1000, in: 25.4 };

/** Working size proposed when a scan is reduced during import. */
export const DEFAULT_REDUCE_TARGET = 1_000_000;
export const MIN_REDUCE_TARGET = 1_000;

export type Size = readonly [number, number, number];

/** Extent of the bounding box in millimetres when the file uses `unit`. */
export function sizeInMillimetres(report: ImportReport, unit: LengthUnit): Size {
  const scale = UNIT_SCALE[unit];
  const [x0, y0, z0] = report.boundsMin;
  const [x1, y1, z1] = report.boundsMax;
  return [(x1 - x0) * scale, (y1 - y0) * scale, (z1 - z0) * scale];
}

/** Extent in the units stored in the file (for the "suspicious size" hint). */
export function sizeInFileUnits(report: ImportReport): Size {
  return sizeInMillimetres(report, 'mm');
}

/** Scan noise in mm as measured for `unit`, or null when the scan is too small to tell. */
export function noiseFor(report: ImportReport, unit: LengthUnit): number | null {
  return report.noise[unit] ?? null;
}

/** The project tolerance the import will set for `unit`. */
export function toleranceFor(report: ImportReport, unit: LengthUnit): number {
  return report.proposedTolerance[unit] ?? DEFAULT_TOLERANCE_MM;
}

/** Target proposed in the reduce field: at most the working limit, below the face count. */
export function defaultReduceTarget(faceCount: number): number {
  return Math.max(MIN_REDUCE_TARGET, Math.min(DEFAULT_REDUCE_TARGET, MAX_WORKING_FACES, faceCount));
}

/** A reduce target is valid inside the kernel's range and below the current face count. */
export function isValidReduceTarget(target: number, faceCount: number): boolean {
  return (
    Number.isInteger(target) &&
    target >= MIN_REDUCE_TARGET &&
    target <= MAX_WORKING_FACES &&
    target < faceCount
  );
}

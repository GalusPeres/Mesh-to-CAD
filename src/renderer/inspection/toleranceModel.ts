// The project tolerance and snap units, edited only in the tolerance popover of the
// status bar (docs/DESIGN.md 3.5).

import type { DocumentSettings } from '@shared/protocol/generated/document-model';
import type { SnapUnits } from '@shared/protocol/generated/snapping';
import type { DocOp } from '@shared/protocol/generated/document-ops';

/**
 * Tolerance steps of the proposal, as in the import (ARCHITECTURE.md 4.12): the first
 * step at or above 2.5 times the scan noise.
 */
export const TOLERANCE_STEPS_MM = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0] as const;
export const NOISE_FACTOR = 2.5;
export const MIN_TOLERANCE_MM = 0.001;
export const MAX_TOLERANCE_MM = 10;

/** The scan noise the proposal uses: the project override, else the import estimate. */
export function effectiveNoise(
  settings: DocumentSettings,
  scanNoise: number | null,
): number | null {
  return settings.noiseOverride ?? scanNoise;
}

export function proposedTolerance(noise: number | null): number | null {
  if (noise === null || !(noise >= 0)) return null;
  const wanted = NOISE_FACTOR * noise;
  return TOLERANCE_STEPS_MM.find((step) => step >= wanted) ?? TOLERANCE_STEPS_MM.at(-1) ?? null;
}

export function isTooTightForNoise(tolerance: number, noise: number | null): boolean {
  return noise !== null && tolerance < NOISE_FACTOR * noise;
}

export function clampTolerance(value: number): number {
  return Math.min(MAX_TOLERANCE_MM, Math.max(MIN_TOLERANCE_MM, value));
}

export interface ToleranceDraft {
  tolerance: number;
  snapUnits: SnapUnits;
}

export function draftChanged(settings: DocumentSettings, draft: ToleranceDraft): boolean {
  return settings.tolerance !== draft.tolerance || settings.snapUnits !== draft.snapUnits;
}

/** The single document operation that changes tolerance and snap units (one revision). */
export function settingsOp(settings: DocumentSettings, draft: ToleranceDraft): DocOp {
  return {
    type: 'setSettings',
    settings: { ...settings, tolerance: draft.tolerance, snapUnits: draft.snapUnits },
  };
}

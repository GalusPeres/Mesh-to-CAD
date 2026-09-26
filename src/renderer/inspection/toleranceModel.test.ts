import { describe, expect, it } from 'vitest';

import type { DocumentSettings } from '@shared/protocol/generated/document-model';

import {
  clampTolerance,
  draftChanged,
  effectiveNoise,
  isTooTightForNoise,
  proposedTolerance,
  settingsOp,
} from './toleranceModel';

const settings: DocumentSettings = {
  tolerance: 0.1,
  snapUnits: 'metric',
  noiseOverride: null,
  deviationMaxDistance: 2,
};

describe('tolerance popover', () => {
  it('proposes the first step at or above 2.5 times the noise, as the import does', () => {
    expect(proposedTolerance(0.036)).toBe(0.1);
    expect(proposedTolerance(0.02)).toBe(0.05);
    expect(proposedTolerance(0.021)).toBe(0.1);
    expect(proposedTolerance(0.1)).toBe(0.25);
    expect(proposedTolerance(2)).toBe(1);
    expect(proposedTolerance(null)).toBeNull();
  });

  it('prefers the project noise override over the import estimate', () => {
    expect(effectiveNoise(settings, 0.036)).toBe(0.036);
    expect(effectiveNoise({ ...settings, noiseOverride: 0.01 }, 0.036)).toBe(0.01);
    expect(effectiveNoise(settings, null)).toBeNull();
  });

  it('warns when the tolerance is tighter than the scanner allows', () => {
    expect(isTooTightForNoise(0.05, 0.036)).toBe(true);
    expect(isTooTightForNoise(0.1, 0.036)).toBe(false);
    expect(isTooTightForNoise(0.01, null)).toBe(false);
  });

  it('keeps the tolerance within sensible limits', () => {
    expect(clampTolerance(0)).toBe(0.001);
    expect(clampTolerance(50)).toBe(10);
    expect(clampTolerance(0.2)).toBe(0.2);
  });

  it('changes tolerance and snap units in one settings operation', () => {
    const draft = { tolerance: 0.15, snapUnits: 'inch' as const };
    expect(draftChanged(settings, { tolerance: 0.1, snapUnits: 'metric' })).toBe(false);
    expect(draftChanged(settings, draft)).toBe(true);
    expect(settingsOp(settings, draft)).toEqual({
      type: 'setSettings',
      settings: { ...settings, tolerance: 0.15, snapUnits: 'inch' },
    });
  });
});

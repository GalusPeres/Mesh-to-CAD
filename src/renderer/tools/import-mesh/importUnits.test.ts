import { describe, expect, it } from 'vitest';

import type { ImportReport } from '@shared/protocol/generated/mesh';

import {
  defaultReduceTarget,
  isValidReduceTarget,
  noiseFor,
  sizeInFileUnits,
  sizeInMillimetres,
  toleranceFor,
} from './importUnits';

const report: ImportReport = {
  pendingId: 'p1',
  fileName: 'halterung_scan.stl',
  faceCount: 3_500_000,
  vertexCount: 1_750_000,
  boundsMin: [-0.06, -0.04, 0],
  boundsMax: [0.06, 0.04, 0.03],
  suggestedUnit: 'm',
  noise: { mm: 0.00004, cm: 0.0004, m: 0.036, in: 0.001 },
  proposedTolerance: { mm: 0.05, cm: 0.05, m: 0.1, in: 0.05 },
  reductionRequired: true,
  counts: { mergedVertices: 8_750_000, nonFiniteFaces: 0 },
};

describe('import units', () => {
  it('scales the bounding box to millimetres for every unit', () => {
    expect(sizeInMillimetres(report, 'm').map((value) => value.toFixed(3))).toEqual([
      '120.000',
      '80.000',
      '30.000',
    ]);
    expect(sizeInMillimetres(report, 'in')[0]).toBeCloseTo(0.12 * 25.4, 12);
    expect(sizeInMillimetres(report, 'cm')[2]).toBeCloseTo(0.3, 12);
    expect(sizeInFileUnits(report)[0]).toBeCloseTo(0.12, 12);
  });

  it('takes noise and tolerance measured for the chosen unit', () => {
    expect(noiseFor(report, 'm')).toBe(0.036);
    expect(toleranceFor(report, 'm')).toBe(0.1);
    expect(noiseFor({ ...report, noise: { mm: null } }, 'mm')).toBeNull();
    expect(toleranceFor({ ...report, proposedTolerance: {} }, 'cm')).toBe(0.1);
  });

  it('proposes a reduce target within the working limit and below the face count', () => {
    expect(defaultReduceTarget(3_500_000)).toBe(1_000_000);
    expect(defaultReduceTarget(400_000)).toBe(400_000);
    expect(isValidReduceTarget(1_000_000, 3_500_000)).toBe(true);
    expect(isValidReduceTarget(2_500_000, 3_500_000)).toBe(false);
    expect(isValidReduceTarget(500, 3_500_000)).toBe(false);
    expect(isValidReduceTarget(400_000, 400_000)).toBe(false);
    expect(isValidReduceTarget(1234.5, 3_500_000)).toBe(false);
  });
});

import { describe, expect, it } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { toggleStep } from '../repairSteps';
import {
  defaultDecimateTarget,
  isValidDecimateTarget,
  scanAvailability,
  uniformStates,
} from './scanEditModel';

describe('scan preparation panels', () => {
  it('propose half the triangles as reduction target, within the limits', () => {
    expect(defaultDecimateTarget(1_204_566)).toBe(602_000);
    expect(defaultDecimateTarget(1_500)).toBe(1_000);
    expect(defaultDecimateTarget(9_000_000)).toBe(2_000_000);
  });

  it('accept only whole targets between 1.000 and the face count', () => {
    expect(isValidDecimateTarget(200_000, 1_204_566)).toBe(true);
    expect(isValidDecimateTarget(1_204_566, 1_204_566)).toBe(false);
    expect(isValidDecimateTarget(999, 1_204_566)).toBe(false);
    expect(isValidDecimateTarget(2_000_001, 9_000_000)).toBe(false);
    expect(isValidDecimateTarget(1500.5, 1_204_566)).toBe(false);
  });

  it('need a scan', () => {
    const empty = { document: { scan: null } } as unknown as DocumentSnapshot;
    const loaded = { document: { scan: { faceCount: 10 } } } as unknown as DocumentSnapshot;
    expect(scanAvailability({ snapshot: null })).toEqual({
      enabled: false,
      reasonKey: 'errors:mesh.noScan',
    });
    expect(scanAvailability({ snapshot: empty }).enabled).toBe(false);
    expect(scanAvailability({ snapshot: loaded }).enabled).toBe(true);
  });

  it('keep the kernel order of repair steps when they are toggled', () => {
    expect(toggleStep(['weld', 'winding'], 'degenerate', true)).toEqual([
      'weld',
      'degenerate',
      'winding',
    ]);
    expect(toggleStep(['weld', 'winding'], 'weld', false)).toEqual(['winding']);
  });

  it('build one face state per face', () => {
    expect(Array.from(uniformStates(3, 2))).toEqual([2, 2, 2]);
  });
});

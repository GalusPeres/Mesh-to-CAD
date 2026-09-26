import { describe, expect, it } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { axisOptions, clampSections, defaultRange, rangeProblem } from './loftDraft';

describe('loft draft', () => {
  it('starts and ends the sections inside the scan', () => {
    expect(defaultRange(0, 60)).toEqual([1.8, 58.2]);
    expect(defaultRange(-10, 0)).toEqual([-9.5, -0.5]);
    expect(defaultRange(0, 0.6)).toEqual([0, 0.6]);
  });

  it('needs an end beyond the start', () => {
    expect(rangeProblem(2, 58)).toBeNull();
    expect(rangeProblem(10, 10)).toBe('emptyRange');
    expect(rangeProblem(30, 10)).toBe('emptyRange');
  });

  it('keeps the section count within 3 to 64', () => {
    expect(clampSections(1)).toBe(3);
    expect(clampSections(12.4)).toBe(12);
    expect(clampSections(100)).toBe(64);
  });

  it('offers global axes, fitted axes and planes that evaluated', () => {
    const snapshot = {
      document: {
        features: [
          { id: 'f1', type: 'fit', name: null, suppressed: false, params: { kind: 'cylinder' } },
          { id: 'f2', type: 'fit', name: null, suppressed: false, params: { kind: 'sphere' } },
          { id: 'f3', type: 'fit', name: null, suppressed: false, params: { kind: 'plane' } },
          { id: 'f4', type: 'fit', name: null, suppressed: false, params: { kind: 'cone' } },
        ],
      },
      status: {
        features: {
          f1: { state: 'ok', issues: [], error: null, stats: {} },
          f2: { state: 'ok', issues: [], error: null, stats: {} },
          f3: { state: 'warning', issues: [], error: null, stats: {} },
          f4: { state: 'error', issues: [], error: null, stats: {} },
        },
        bodies: [],
      },
    } as unknown as Pick<DocumentSnapshot, 'document' | 'status'>;
    expect(axisOptions(snapshot, null)).toEqual(['X', 'Y', 'Z', 'f1', 'f3']);
    expect(axisOptions(snapshot, 'f3')).toEqual(['X', 'Y', 'Z', 'f1']);
  });
});

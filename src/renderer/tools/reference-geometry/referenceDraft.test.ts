import { describe, expect, it } from 'vitest';

import { angleZeroDirection } from '../../features/reference/geometry';
import {
  EMPTY_REFERENCE,
  definitionOf,
  draftOf,
  nextEmptySlot,
  originInputs,
  withInput,
  withType,
} from './referenceDraft';

describe('reference draft', () => {
  it('needs every input before it has a definition', () => {
    const draft = withType(EMPTY_REFERENCE, 'midPlane');
    expect(definitionOf(draft)).toBeNull();
    expect(nextEmptySlot(draft)).toBe('a');
    const one = withInput(draft, 'a', 'f2');
    expect(nextEmptySlot(one)).toBe('b');
    expect(definitionOf(withInput(one, 'b', 'f5'))).toEqual({ type: 'midPlane', a: 'f2', b: 'f5' });
  });

  it('keeps inputs that still fit a new definition', () => {
    const mid = withInput(withInput(withType(EMPTY_REFERENCE, 'midPlane'), 'a', 'f2'), 'b', 'f5');
    expect(withType(mid, 'axisFromPlanes').inputs).toEqual({ a: 'f2', b: 'f5' });
    expect(withType(mid, 'planeThroughAxis').inputs).toEqual({});
  });

  it('carries distance and angle', () => {
    const offset = withInput({ ...EMPTY_REFERENCE, distance: 5 }, 'plane', 'XY');
    expect(definitionOf(offset)).toEqual({ type: 'offsetPlane', plane: 'XY', distance: 5 });
    const through = withInput(
      { ...withType(EMPTY_REFERENCE, 'planeThroughAxis'), angleDeg: 30 },
      'axis',
      'f1',
    );
    expect(definitionOf(through)).toEqual({ type: 'planeThroughAxis', axis: 'f1', angleDeg: 30 });
  });

  it('round-trips stored definitions', () => {
    const stored = { type: 'planeThroughAxis', axis: 'f3', angleDeg: 45 } as const;
    expect(definitionOf(draftOf(stored))).toEqual(stored);
    const offset = { type: 'offsetPlane', plane: 'f1', distance: -2 } as const;
    expect(definitionOf(draftOf(offset))).toEqual(offset);
  });

  it('offers the origin planes and axes', () => {
    expect(originInputs('plane')).toEqual(['XY', 'YZ', 'XZ']);
    expect(originInputs('axis')).toEqual(['X', 'Y', 'Z']);
  });
});

describe('angle zero direction', () => {
  it('matches the kernel rule: X, or Y for axes near X', () => {
    expect(angleZeroDirection([0, 0, 1])).toEqual([1, 0, 0]);
    expect(angleZeroDirection([1, 0, 0])).toEqual([0, 1, 0]);
    const tilted = angleZeroDirection([0, 0.6, 0.8]);
    expect(tilted[0]).toBeCloseTo(1, 12);
  });
});

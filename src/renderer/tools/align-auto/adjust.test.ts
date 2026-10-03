import { describe, expect, it } from 'vitest';

import {
  NO_ADJUST,
  applyAdjust,
  isAdjusted,
  normalisedQuarters,
  rotationDegrees,
  sameAdjust,
} from './adjust';

describe('alignment adjustments', () => {
  it('toggles the flips and leaves the other values alone', () => {
    const turned = applyAdjust(NO_ADJUST, 'flipZ');
    expect(turned).toEqual({ flipX: false, flipZ: true, rotateZ90: 0 });
    expect(applyAdjust(turned, 'flipX')).toEqual({ flipX: true, flipZ: true, rotateZ90: 0 });
    expect(applyAdjust(turned, 'flipZ')).toEqual(NO_ADJUST);
  });

  it('rotates in quarter turns and wraps after a full turn', () => {
    let adjust = NO_ADJUST;
    const degrees: number[] = [];
    for (let step = 0; step < 5; step += 1) {
      adjust = applyAdjust(adjust, 'rotate');
      degrees.push(rotationDegrees(adjust));
    }
    expect(degrees).toEqual([90, 180, 270, 0, 90]);
  });

  it('normalises stored quarter turns outside 0..3', () => {
    expect(normalisedQuarters(-1)).toBe(3);
    expect(normalisedQuarters(6)).toBe(2);
    expect(applyAdjust({ ...NO_ADJUST, rotateZ90: 7 }, 'rotate').rotateZ90).toBe(0);
  });

  it('knows whether anything is adjusted', () => {
    expect(isAdjusted(NO_ADJUST)).toBe(false);
    expect(isAdjusted({ ...NO_ADJUST, rotateZ90: 4 })).toBe(false);
    expect(isAdjusted({ ...NO_ADJUST, flipX: true })).toBe(true);
    expect(sameAdjust({ ...NO_ADJUST, rotateZ90: 5 }, { ...NO_ADJUST, rotateZ90: 1 })).toBe(true);
  });
});

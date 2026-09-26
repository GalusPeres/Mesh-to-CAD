import { describe, expect, it } from 'vitest';

import { angleAround, closestAlongAxis, intersectPlane } from './handles';

describe('handle drag maths', () => {
  it('finds the axis parameter closest to a ray', () => {
    const t = closestAlongAxis([0, 0, 0], [0, 0, 1], { origin: [10, 0, 5], direction: [-1, 0, 0] });
    expect(t).toBeCloseTo(5);
  });

  it('intersects a ray with a plane', () => {
    const hit = intersectPlane({ origin: [1, 2, 10], direction: [0, 0, -1] }, [0, 0, 3], [0, 0, 1]);
    expect(hit).toEqual([1, 2, 3]);
    expect(
      intersectPlane({ origin: [0, 0, 1], direction: [1, 0, 0] }, [0, 0, 0], [0, 0, 1]),
    ).toBeNull();
  });

  it('measures angles around an axis from the reference direction', () => {
    expect(angleAround([0, 5, 0], [0, 0, 0], [0, 0, 1], [1, 0, 0])).toBeCloseTo(90);
    expect(angleAround([-5, 0, 0], [0, 0, 0], [0, 0, 1], [1, 0, 0])).toBeCloseTo(180);
  });
});

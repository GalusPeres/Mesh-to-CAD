import { describe, expect, it } from 'vitest';

import {
  STANDARD_VIEWS,
  boxSphere,
  cameraPosition,
  orthographicHalfHeight,
  perspectiveDistance,
} from './cameraMath';

const dot = (a: readonly number[], b: readonly number[]) =>
  a.reduce((sum, value, index) => sum + value * (b[index] ?? 0), 0);

describe('standard views', () => {
  it('look along unit directions with an up vector that is not parallel to them', () => {
    for (const { direction, up } of Object.values(STANDARD_VIEWS)) {
      expect(Math.hypot(...direction)).toBeCloseTo(1);
      expect(Math.abs(dot(direction, up))).toBeLessThan(0.9);
    }
  });

  it('follow the CAD convention with Z up', () => {
    expect(STANDARD_VIEWS.front.direction).toEqual([0, 1, 0]);
    expect(STANDARD_VIEWS.top.direction).toEqual([0, 0, -1]);
    expect(STANDARD_VIEWS.front.up).toEqual([0, 0, 1]);
  });

  it('place the iso camera in front, right and above', () => {
    const position = cameraPosition([0, 0, 0], STANDARD_VIEWS.iso.direction, 10);
    expect(position[0]).toBeGreaterThan(0);
    expect(position[1]).toBeLessThan(0);
    expect(position[2]).toBeGreaterThan(0);
  });
});

describe('fitting', () => {
  it('encloses a box in a sphere', () => {
    const sphere = boxSphere([0, 0, 0], [100, 70, 20]);
    expect(sphere.center).toEqual([50, 35, 10]);
    expect(sphere.radius).toBeCloseTo(Math.hypot(100, 70, 20) / 2);
  });

  it('moves a perspective camera far enough for narrow windows', () => {
    expect(perspectiveDistance(10, 45, 0.5)).toBeGreaterThan(perspectiveDistance(10, 45, 2));
  });

  it('sizes an orthographic frustum with a margin', () => {
    expect(orthographicHalfHeight(10, 2)).toBeCloseTo(11);
    expect(orthographicHalfHeight(10, 0.5)).toBeCloseTo(22);
  });
});

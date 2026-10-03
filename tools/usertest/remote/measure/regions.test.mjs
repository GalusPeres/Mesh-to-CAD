import { describe, expect, it } from 'vitest';

import { compare } from '../report.mjs';
import { classify } from './regions.mjs';

const [LENGTH, WIDTH, HEIGHT] = [40, 80, 10];
const BUTTON = { centre: [20, 40], radius: 4, height: 1 };
const STEP = 0.3;

/** Points and normals on a box with a round button on its top. */
function boxWithButton() {
  const points = [];
  const normals = [];
  const add = (point, normal) => {
    points.push(...point);
    normals.push(...normal);
  };
  const onButton = (x, y) => Math.hypot(x - BUTTON.centre[0], y - BUTTON.centre[1]) < BUTTON.radius;
  for (let x = 0; x <= LENGTH; x += STEP) {
    for (let y = 0; y <= WIDTH; y += STEP) {
      add([x, y, 0], [0, 0, -1]);
      add([x, y, onButton(x, y) ? HEIGHT + BUTTON.height : HEIGHT], [0, 0, 1]);
    }
  }
  for (let z = STEP; z < HEIGHT; z += STEP) {
    for (let x = 0; x <= LENGTH; x += STEP) {
      add([x, 0, z], [0, -1, 0]);
      add([x, WIDTH, z], [0, 1, 0]);
    }
    for (let y = 0; y <= WIDTH; y += STEP) {
      add([0, y, z], [-1, 0, 0]);
      add([LENGTH, y, z], [1, 0, 0]);
    }
  }
  return { points: Float32Array.from(points), normals: Float32Array.from(normals) };
}

const PLANES = {
  top: { origin: [0, 0, HEIGHT], normal: [0, 0, 1] },
  bottom: { origin: [0, 0, 0], normal: [0, 0, -1] },
};

describe('the regions of the remote pipeline', () => {
  const { points, normals } = boxWithButton();
  const { region, regions } = classify(points, normals, PLANES, [
    { shape: 'circle', at: [20, 40, HEIGHT + BUTTON.height] },
  ]);
  /** The region name of the point nearest to `at`. */
  const at = (target) => {
    let best = -1;
    let distance = Infinity;
    for (let i = 0; i < points.length / 3; i += 1) {
      const d = Math.hypot(
        points[i * 3] - target[0],
        points[i * 3 + 1] - target[1],
        points[i * 3 + 2] - target[2],
      );
      if (d < distance) [best, distance] = [i, d];
    }
    return regions[region[best]].name;
  };

  it('sorts the box into underside, walls, corners, top edge and top face', () => {
    expect(at([20, 40, 0])).toBe('underside');
    expect(at([0, 40, 5])).toBe('walls');
    expect(at([0, 2, 5])).toBe('corner front-left');
    expect(at([40, 78, 5])).toBe('corner back-right');
    expect(at([0, 40, 9.4])).toBe('top edge');
    expect(at([20, 20, 10])).toBe('top face');
  });

  it('makes the recognised button a region of its own, named by shape and place', () => {
    expect(at([20, 40, 11])).toBe('circle x20 y40');
    expect(regions.filter((item) => item.shapes.length > 0)).toHaveLength(1);
  });
});

describe('comparing two runs', () => {
  const run = (within, centre) => ({
    measure: {
      regions: [
        { name: 'walls', within, rms: 0.05, max: { value: 0.3 }, uncovered: 0 },
        { name: `circle x${centre}`, centre: [centre, 40], within: 0.5, rms: 0.1, uncovered: 0 },
      ],
    },
  });

  it('names what got better and matches shapes by their place', () => {
    const lines = compare(run(0.5, 20), run(0.8, 20.4));
    expect(lines).toEqual(['better  walls: +30.0 pt within']);
  });
});

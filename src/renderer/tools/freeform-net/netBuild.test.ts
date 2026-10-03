import { describe, expect, it } from 'vitest';

import type { Vec3 } from '../../viewport/api';
import {
  addQuad,
  borderChain,
  borderEdges,
  extrudeEdges,
  keptRun,
  outwardSteps,
  splitRing,
  walkOnSurface,
} from './netBuild';
import type { Net } from './netModel';

const UP: Vec3 = [0, 0, 1];

/** A 2 x 1 strip in the XY plane: bottom 0 1 2, top 3 4 5. */
function strip(): Net {
  const points = [0, 0, 0, 1, 0, 0, 2, 0, 0, 0, 1, 0, 1, 1, 0, 2, 1, 0];
  return { vertices: Float64Array.from(points), quads: Uint32Array.from([0, 1, 4, 3, 1, 2, 5, 4]) };
}

/** Every edge is used once, or twice in opposite directions (a consistently oriented net). */
function expectOriented(net: Net): void {
  const directed = new Map<string, number>();
  for (let quad = 0; quad < net.quads.length / 4; quad += 1) {
    for (let k = 0; k < 4; k += 1) {
      const a = net.quads[quad * 4 + k];
      const b = net.quads[quad * 4 + ((k + 1) % 4)];
      const id = `${a},${b}`;
      expect(directed.has(id), `edge ${id} used twice in one direction`).toBe(false);
      directed.set(id, quad);
    }
  }
}

function normalOf(net: Net, quad: number): Vec3 {
  const p = (i: number): Vec3 => {
    const v = net.quads[quad * 4 + i] ?? 0;
    return [net.vertices[v * 3] ?? 0, net.vertices[v * 3 + 1] ?? 0, net.vertices[v * 3 + 2] ?? 0];
  };
  const [a, b, c] = [p(0), p(1), p(2)];
  const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const w = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
  return [
    u[1]! * w[2]! - u[2]! * w[1]!,
    u[2]! * w[0]! - u[0]! * w[2]!,
    u[0]! * w[1]! - u[1]! * w[0]!,
  ];
}

describe('building a net by hand', () => {
  it('turns a clicked face towards the outside of the scan', () => {
    const clockwise: Vec3[] = [
      [0, 0, 0],
      [0, 1, 0],
      [1, 1, 0],
      [1, 0, 0],
    ];
    const net = addQuad(null, clockwise, UP);
    expect(normalOf(net, 0)[2]).toBeGreaterThan(0);
    const two = addQuad(
      net,
      clockwise.map(([x, y]) => [x + 3, y, 0] as Vec3),
      UP,
    );
    expect(two.quads.length).toBe(8);
    expect(normalOf(two, 1)[2]).toBeGreaterThan(0);
  });

  it('follows a border up to the corners of the net', () => {
    const net = strip();
    expect(borderEdges(net)).toHaveLength(6);
    // The bottom side runs 0 -> 1 -> 2; the middle point has two quads.
    expect(borderChain(net, { a: 1, b: 2 })).toEqual([
      { a: 0, b: 1 },
      { a: 1, b: 2 },
    ]);
    // The short side ends at corners right away.
    expect(borderChain(net, { a: 2, b: 5 })).toEqual([{ a: 2, b: 5 }]);
  });

  it('drags a new row out of a border chain, oriented like its neighbours', () => {
    const net = strip();
    const chain = borderChain(net, { a: 0, b: 1 });
    const result = extrudeEdges(net, chain, (vertex) => [net.vertices[vertex * 3] ?? 0, -1, 0]);
    expect(result.added).toEqual([6, 7, 8]);
    expect(result.net.quads.length / 4).toBe(4);
    expectOriented(result.net);
    for (let quad = 0; quad < 4; quad += 1)
      expect(normalOf(result.net, quad)[2]).toBeGreaterThan(0);
    // The old bottom is inside now; the new bottom is border.
    expect(borderEdges(result.net)).toHaveLength(8);
  });

  it('grows rows outward along the surface, mitred at corners', () => {
    const net = strip();
    const pointOf = (v: number): Vec3 => [
      net.vertices[v * 3] ?? 0,
      net.vertices[v * 3 + 1] ?? 0,
      net.vertices[v * 3 + 2] ?? 0,
    ];
    const bottom = outwardSteps(borderChain(net, { a: 0, b: 1 }), pointOf, () => UP);
    for (const v of [0, 1, 2]) expect(bottom.get(v)?.[1]).toBeCloseTo(-1);
    // Around the corners: the whole border, the corner points move diagonally.
    const loop = borderChain(net, { a: 0, b: 1 }, true);
    expect(loop).toHaveLength(6);
    const steps = outwardSteps(loop, pointOf, () => UP);
    expect(steps.get(0)?.[0]).toBeCloseTo(-1);
    expect(steps.get(0)?.[1]).toBeCloseTo(-1);
    expect(steps.get(1)?.[1]).toBeCloseTo(-1);
    const ring = extrudeEdges(net, loop, (v) => {
      const p = pointOf(v);
      const step = steps.get(v) ?? [0, 0, 0];
      return [p[0] + step[0], p[1] + step[1], 0];
    });
    expect(ring.net.quads.length / 4).toBe(2 + 6);
    expectOriented(ring.net);
  });

  it('takes the sides of a border that face one way, round the loop start', () => {
    const net = strip();
    const loop = borderChain(net, { a: 0, b: 1 }, true);
    const keep = (edges: [number, number][]) =>
      loop.map((edge) => edges.some(([a, b]) => edge.a === a && edge.b === b));
    // Bottom and left side: the corner at point 0 between them.
    const corner = keptRun(
      loop,
      keep([
        [0, 1],
        [1, 2],
        [3, 0],
      ]),
      { a: 1, b: 2 },
    );
    expect(corner).toHaveLength(3);
    expect(corner.map((e) => e.a)).toContain(3);
    for (let i = 1; i < corner.length; i += 1) expect(corner[i]?.a).toBe(corner[i - 1]?.b);
    expect(keptRun(loop, keep([[0, 1]]), { a: 1, b: 2 })).toEqual([]);
    expect(
      keptRun(
        loop,
        loop.map(() => true),
        { a: 0, b: 1 },
      ),
    ).toHaveLength(6);
  });

  it('walks over a rounded edge and down the wall', () => {
    // Top z = 0 for x <= 0, a fillet of radius 1 about (0, y, -1), the wall x = 1 below.
    const rounded = (p: Vec3) => {
      const [x, y, z] = p;
      if (x <= 0) return { point: [x, y, 0] as Vec3, normal: [0, 0, 1] as Vec3 };
      if (z <= -1) return { point: [1, y, z] as Vec3, normal: [1, 0, 0] as Vec3 };
      const r = Math.hypot(x, z + 1) || 1;
      return {
        point: [x / r, y, -1 + (z + 1) / r] as Vec3,
        normal: [x / r, 0, (z + 1) / r] as Vec3,
      };
    };
    // 1 on the top, a quarter circle (pi / 2), 1 down the wall.
    const end = walkOnSurface([-1, 0, 0], [1, 0, 0], 2 + Math.PI / 2, rounded, 0.05);
    expect(end[0]).toBeCloseTo(1, 1);
    expect(end[2]).toBeGreaterThan(-2.2);
    expect(end[2]).toBeLessThan(-1.8);
    // A step straight out would have stopped on the rounding.
    const straight = rounded([-1 + 2 + Math.PI / 2, 0, 0]).point;
    expect(straight[2]).toBeGreaterThan(-1);
  });

  it('splits the ring of quads crossing an edge', () => {
    // Crossing the left side 0-3 splits both quads lengthwise.
    const across = splitRing(strip(), 0, 3);
    expect(across.added).toHaveLength(3);
    expect(across.net.quads.length / 4).toBe(4);
    expectOriented(across.net);
    // Crossing the bottom edge 0-1 splits only the first quad.
    const one = splitRing(strip(), 0, 1);
    expect(one.added).toHaveLength(2);
    expect(one.net.quads.length / 4).toBe(3);
    expectOriented(one.net);
    expect(splitRing(strip(), 0, 5).added).toEqual([]);
  });

  it('closes the ring of a closed band', () => {
    // A band of four quads around the Z axis (a square tube without caps).
    const ring: number[] = [];
    const square: [number, number][] = [
      [1, 1],
      [-1, 1],
      [-1, -1],
      [1, -1],
    ];
    for (const z of [0, 1]) for (const [x, y] of square) ring.push(x, y, z);
    const quads: number[] = [];
    for (let i = 0; i < 4; i += 1) quads.push(i, (i + 1) % 4, ((i + 1) % 4) + 4, i + 4);
    const band: Net = { vertices: Float64Array.from(ring), quads: Uint32Array.from(quads) };
    expectOriented(band);
    // A loop round the band: every quad is split, four new points.
    const around = splitRing(band, 0, 4);
    expect(around.added).toHaveLength(4);
    expect(around.net.quads.length / 4).toBe(8);
    expectOriented(around.net);
  });
});

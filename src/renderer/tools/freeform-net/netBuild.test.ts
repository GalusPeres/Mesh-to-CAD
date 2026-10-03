import { describe, expect, it } from 'vitest';

import type { Vec3 } from '../../viewport/api';
import {
  addQuad,
  bridgeRuns,
  extrudeEdges,
  mergePoints,
  removeQuads,
  splitRing,
  subdivide,
} from './netBuild';
import type { Net } from './netModel';
import { borderChain, borderEdges, borderRuns, edgeLoop } from './netTopology';

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

  it('continues from the outside of a new row', () => {
    const net = strip();
    const row = extrudeEdges(net, [{ a: 0, b: 1 }], (vertex) => [
      net.vertices[vertex * 3] ?? 0,
      -1,
      0,
    ]);
    // The new row's outer edge is border, directed as in its quad: dragged again it grows on.
    expect(row.outer).toEqual([{ a: 6, b: 7 }]);
    const border = borderEdges(row.net);
    expect(border).toContainEqual({ a: 6, b: 7 });
    const again = extrudeEdges(row.net, row.outer, (vertex) => [
      row.net.vertices[vertex * 3] ?? 0,
      -2,
      0,
    ]);
    expectOriented(again.net);
  });

  it('orders chosen border edges into runs', () => {
    const net = strip();
    // Bottom 1-2, right side 2-5 and top 4-3 (chosen in any order and direction).
    const runs = borderRuns(net, [
      { a: 3, b: 4 },
      { a: 5, b: 2 },
      { a: 1, b: 2 },
      { a: 1, b: 4 },
    ]);
    expect(runs).toHaveLength(2);
    const corner = runs.find((run) => run.length === 2);
    expect(corner).toEqual([
      { a: 1, b: 2 },
      { a: 2, b: 5 },
    ]);
    expect(runs.find((run) => run.length === 1)).toEqual([{ a: 4, b: 3 }]);
    // The whole border is one closed run.
    expect(borderRuns(net, borderEdges(net))).toHaveLength(1);
  });

  it('selects the edge loop through regular points', () => {
    // A 3 x 3 grid: point (i, j) is j * 4 + i, quads counter-clockwise.
    const vertices: number[] = [];
    for (let j = 0; j < 4; j += 1) for (let i = 0; i < 4; i += 1) vertices.push(i, j, 0);
    const quads: number[] = [];
    for (let j = 0; j < 3; j += 1)
      for (let i = 0; i < 3; i += 1) {
        const p = j * 4 + i;
        quads.push(p, p + 1, p + 5, p + 4);
      }
    const grid: Net = { vertices: Float64Array.from(vertices), quads: Uint32Array.from(quads) };
    // Row 1, from the inner edge 5-6 out to the border on both sides.
    expect(edgeLoop(grid, { a: 5, b: 6 })).toEqual([
      { a: 4, b: 5 },
      { a: 5, b: 6 },
      { a: 6, b: 7 },
    ]);
    // A border edge selects its side up to the corners.
    expect(edgeLoop(grid, { a: 1, b: 2 })).toHaveLength(3);
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

describe('joining pieces of a net', () => {
  /** Two unit quads side by side with a gap: left 0 1 2 3, right 4 5 6 7 (from x = 2). */
  function apart(): Net {
    const points = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 2, 0, 0, 3, 0, 0, 3, 1, 0, 2, 1, 0];
    return {
      vertices: Float64Array.from(points),
      quads: Uint32Array.from([0, 1, 2, 3, 4, 5, 6, 7]),
    };
  }

  it('bridges two pieces when a row is dropped onto the other border', () => {
    const net = apart();
    // The left piece's right side 1 -> 2 dropped onto the right piece's left side 7 -> 4.
    const bridge = extrudeEdges(net, [{ a: 1, b: 2 }], (vertex) =>
      vertex === 1 ? { onto: 4 } : { onto: 7 },
    );
    expect(bridge.added).toEqual([]);
    expect(bridge.net.vertices.length).toBe(net.vertices.length);
    expect(bridge.net.quads.length / 4).toBe(3);
    expectOriented(bridge.net);
    // One piece now: the old gap sides are inside, the border is one loop of eight edges.
    expect(borderEdges(bridge.net)).toHaveLength(8);
    expect(borderRuns(bridge.net, borderEdges(bridge.net))).toHaveLength(1);
  });

  it('leaves out a quad that would collapse', () => {
    const net = apart();
    const row = extrudeEdges(net, [{ a: 1, b: 2 }], () => ({ onto: 4 }));
    expect(row.net.quads.length).toBe(net.quads.length);
  });

  it('welds two border points into one', () => {
    const net = apart();
    // Point 1 (left piece) onto point 4 (right piece): the pieces touch at one corner.
    const welded = mergePoints(net, 1, 4);
    expect(welded).not.toBeNull();
    expect(welded?.vertices.length).toBe(net.vertices.length - 3);
    expect(welded?.quads.length).toBe(8);
    expectOriented(welded as Net);
    // Two corners of one quad cannot become one point.
    expect(mergePoints(net, 0, 1)).toBeNull();
  });

  it('deletes quads and the points only they used', () => {
    const net = strip();
    // The quad using point 0 goes, and with it points 0 and 3; the rest is renumbered.
    const rest = removeQuads(net, (corners) => corners.includes(0));
    expect(rest?.quads.length).toBe(4);
    expect(rest?.vertices.length).toBe(4 * 3);
    expectOriented(rest as Net);
    expect(removeQuads(net, () => true)?.quads.length).toBe(0);
    expect(removeQuads(net, () => false)).toBeNull();
  });

  it('bridges two chosen edges with a quad', () => {
    const net = apart();
    // The left piece's right side 1 -> 2 and the right piece's left side 7 -> 4.
    const bridged = bridgeRuns(net, [{ a: 1, b: 2 }], [{ a: 7, b: 4 }]);
    expect(bridged?.quads.length).toBe(12);
    expect(bridged?.vertices.length).toBe(net.vertices.length);
    expectOriented(bridged as Net);
    expect(bridgeRuns(net, [{ a: 1, b: 2 }], [])).toBeNull();
  });

  it('splits every quad into four', () => {
    const fine = subdivide(strip());
    // Two quads become eight; 6 old points + 7 edge middles + 2 quad middles.
    expect(fine.net.quads.length / 4).toBe(8);
    expect(fine.net.vertices.length / 3).toBe(15);
    expect(fine.added).toHaveLength(9);
    expectOriented(fine.net);
    for (let quad = 0; quad < 8; quad += 1) expect(normalOf(fine.net, quad)[2]).toBeGreaterThan(0);
  });
});

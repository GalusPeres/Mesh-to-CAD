// A regular net for the unit tests: an n x n grid of control points in the plane z = 0
// and its limit map as the kernel builds it for a regular Catmull-Clark net (uniform
// bicubic B-splines). Dense vertex i < n * n is the limit point of control point i;
// after them come samples inside the inner quads, at quarter steps.

import type { LimitMapResult } from '@shared/protocol/generated/net';

import type { Net } from './netModel';

const basis = (t: number): number[] => [
  (1 - t) ** 3 / 6,
  (3 * t ** 3 - 6 * t ** 2 + 4) / 6,
  (-3 * t ** 3 + 3 * t ** 2 + 3 * t + 1) / 6,
  t ** 3 / 6,
];

export interface GridFixture {
  n: number;
  net: Net;
  map: LimitMapResult;
  /** Grid position (i, j) of every dense vertex, in control-point units. */
  at: [number, number][];
  id: (i: number, j: number) => number;
}

export function gridFixture(n: number): GridFixture {
  const id = (i: number, j: number) => i * n + j;
  const rows: [number, number][][] = [];
  const at: [number, number][] = [];
  const line = (k: number, last: number) =>
    k === 0 || k === last
      ? [[k, 1]]
      : [
          [k - 1, 1 / 6],
          [k, 4 / 6],
          [k + 1, 1 / 6],
        ];
  // Limit points: tensor masks; along the border the crease rule (a cubic B-spline curve).
  for (let i = 0; i < n; i += 1)
    for (let j = 0; j < n; j += 1) {
      const row: [number, number][] = [];
      for (const [a, wa] of line(i, n - 1))
        for (const [b, wb] of line(j, n - 1)) row.push([id(a!, b!), wa! * wb!]);
      rows.push(row);
      at.push([i, j]);
    }
  // Samples inside the quads whose 4 x 4 control points all exist.
  for (let i = 1; i < n - 2; i += 1)
    for (let j = 1; j < n - 2; j += 1)
      for (const u of [0, 0.25, 0.5, 0.75])
        for (const v of [0, 0.25, 0.5, 0.75]) {
          if (u === 0 && v === 0) continue;
          const [bu, bv] = [basis(u), basis(v)];
          const row: [number, number][] = [];
          for (let a = 0; a < 4; a += 1)
            for (let b = 0; b < 4; b += 1) row.push([id(i - 1 + a, j - 1 + b), bu[a]! * bv[b]!]);
          rows.push(row);
          at.push([i + u, j + v]);
        }
  const quads: number[] = [];
  for (let i = 0; i < n - 1; i += 1)
    for (let j = 0; j < n - 1; j += 1)
      quads.push(id(i, j), id(i + 1, j), id(i + 1, j + 1), id(i, j + 1));
  const vertices = new Float64Array(n * n * 3);
  for (let i = 0; i < n; i += 1)
    for (let j = 0; j < n; j += 1) vertices.set([i, j, 0], id(i, j) * 3);
  const indptr = [0];
  const columns: number[] = [];
  const weights: number[] = [];
  for (const row of rows) {
    for (const [column, weight] of row) {
      columns.push(column);
      weights.push(weight);
    }
    indptr.push(columns.length);
  }
  const map: LimitMapResult = {
    rows: Uint32Array.from(indptr),
    columns: Uint32Array.from(columns),
    weights: Float32Array.from(weights),
    triangles: new Uint32Array(),
    segments: new Uint32Array(),
    segmentEdges: new Uint32Array(),
    edges: new Uint32Array(),
    boundaryEdges: new Uint8Array(),
    border: new Uint8Array(rows.length),
    faceEdges: new Uint8Array(),
    faceCount: 1,
    level: 2,
    fineCount: rows.length,
  };
  return { n, net: { vertices, quads: Uint32Array.from(quads) }, map, at, id };
}

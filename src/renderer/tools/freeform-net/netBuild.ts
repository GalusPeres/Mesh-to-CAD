// Building a net by hand, as in QuickSurface: a face from four clicked points, a new
// row of faces dragged out of a border edge (or a whole border chain), and a new
// loop through a ring of faces (S). Every operation keeps the net made of quads,
// oriented alike, so its rows stay aligned and its surface stays smooth.

import type { Vec3 } from '../../viewport/api';
import type { Net } from './netModel';

/** An edge of a quad, directed as in that quad (counter-clockwise seen from outside). */
export interface Edge {
  a: number;
  b: number;
}

const key = (a: number, b: number): string => (a < b ? `${a},${b}` : `${b},${a}`);

function quadCount(net: Net): number {
  return net.quads.length / 4;
}

function corner(net: Net, quad: number, k: number): number {
  return net.quads[quad * 4 + (k % 4)] ?? 0;
}

function point(net: Net, vertex: number): Vec3 {
  return [
    net.vertices[vertex * 3] ?? 0,
    net.vertices[vertex * 3 + 1] ?? 0,
    net.vertices[vertex * 3 + 2] ?? 0,
  ];
}

/** Quads (and the edge's position k in each) by undirected edge. */
function edgeQuads(net: Net): Map<string, { quad: number; k: number }[]> {
  const result = new Map<string, { quad: number; k: number }[]>();
  for (let quad = 0; quad < quadCount(net); quad += 1) {
    for (let k = 0; k < 4; k += 1) {
      const id = key(corner(net, quad, k), corner(net, quad, k + 1));
      const list = result.get(id);
      if (list) list.push({ quad, k });
      else result.set(id, [{ quad, k }]);
    }
  }
  return result;
}

/** Edges used by one quad only, directed as in that quad. */
export function borderEdges(net: Net): Edge[] {
  const edges: Edge[] = [];
  for (const users of edgeQuads(net).values()) {
    const only = users.length === 1 ? users[0] : undefined;
    if (only)
      edges.push({ a: corner(net, only.quad, only.k), b: corner(net, only.quad, only.k + 1) });
  }
  return edges;
}

/** A net with one quad more, from four new points, facing `outward`. */
export function addQuad(net: Net | null, corners: readonly Vec3[], outward: Vec3): Net {
  if (corners.length !== 4) throw new Error('a face needs four corners');
  // Newell normal of the polygon; the quad turns counter-clockwise seen from outside.
  let nx = 0;
  let ny = 0;
  let nz = 0;
  corners.forEach((current, i) => {
    const next = corners[(i + 1) % 4] as Vec3;
    nx += (current[1] - next[1]) * (current[2] + next[2]);
    ny += (current[2] - next[2]) * (current[0] + next[0]);
    nz += (current[0] - next[0]) * (current[1] + next[1]);
  });
  const ordered =
    nx * outward[0] + ny * outward[1] + nz * outward[2] >= 0 ? corners : [...corners].reverse();
  const base = net ? net.vertices.length / 3 : 0;
  const vertices = new Float64Array((base + 4) * 3);
  if (net) vertices.set(net.vertices);
  ordered.forEach((corner, i) => vertices.set(corner, (base + i) * 3));
  const quads = new Uint32Array((net ? net.quads.length : 0) + 4);
  if (net) quads.set(net.quads);
  quads.set([base, base + 1, base + 2, base + 3], quads.length - 4);
  return { vertices, quads };
}

/**
 * The border chain through a border edge: the border edges before and after it up to
 * the net's corners (border points with one quad), or with `aroundCorners` the whole
 * border loop it belongs to.
 */
export function borderChain(net: Net, edge: Edge, aroundCorners = false): Edge[] {
  const border = borderEdges(net);
  const starting = new Map<number, Edge>();
  const ending = new Map<number, Edge>();
  for (const item of border) {
    starting.set(item.a, item);
    ending.set(item.b, item);
  }
  const quadsAt = new Map<number, number>();
  for (const vertex of net.quads) quadsAt.set(vertex, (quadsAt.get(vertex) ?? 0) + 1);
  // A corner of the net (one quad) ends the chain; a regular border point has two.
  const passes = (vertex: number) => aroundCorners || (quadsAt.get(vertex) ?? 0) === 2;
  const chain: Edge[] = [edge];
  const seen = new Set([key(edge.a, edge.b)]);
  for (let current = edge; passes(current.b);) {
    const next = starting.get(current.b);
    if (!next || seen.has(key(next.a, next.b))) break;
    seen.add(key(next.a, next.b));
    chain.push(next);
    current = next;
  }
  for (let current = edge; passes(current.a);) {
    const previous = ending.get(current.a);
    if (!previous || seen.has(key(previous.a, previous.b))) break;
    seen.add(key(previous.a, previous.b));
    chain.unshift(previous);
    current = previous;
  }
  return chain;
}

/**
 * A new row of quads along border edges (consecutive, as `borderChain` gives them):
 * every chain point gets a new point at `positions(point)`, and every edge a quad
 * between them, oriented like its neighbour. Returns the net and the new points.
 */
export function extrudeEdges(
  net: Net,
  chain: readonly Edge[],
  positions: (vertex: number) => Vec3,
): { net: Net; added: number[] } {
  const points: number[] = [];
  chain.forEach((edge, i) => {
    if (i === 0) points.push(edge.a);
    points.push(edge.b);
  });
  const closed = points.length > 2 && points[0] === points[points.length - 1];
  if (closed) points.pop();
  const base = net.vertices.length / 3;
  const copy = new Map<number, number>();
  points.forEach((vertex, i) => copy.set(vertex, base + i));
  const vertices = new Float64Array((base + points.length) * 3);
  vertices.set(net.vertices);
  points.forEach((vertex, i) => vertices.set(positions(vertex), (base + i) * 3));
  const quads = new Uint32Array(net.quads.length + chain.length * 4);
  quads.set(net.quads);
  chain.forEach(({ a, b }, i) => {
    // The neighbour runs a -> b, so the new quad runs b -> a.
    quads.set([b, a, copy.get(a) ?? a, copy.get(b) ?? b], net.quads.length + i * 4);
  });
  return { net: { vertices, quads }, added: points.map((vertex) => copy.get(vertex) ?? vertex) };
}

/**
 * A new loop through the ring of quads that cross the edge a-b: every crossed edge
 * gets its midpoint, and every quad of the ring becomes two. Returns the net and the
 * new points (empty if a-b is no edge).
 */
export function splitRing(net: Net, a: number, b: number): { net: Net; added: number[] } {
  const users = edgeQuads(net);
  const start = users.get(key(a, b));
  if (!start) return { net, added: [] };
  // Walk across the ring in both directions from the edge.
  const crossing = new Map<number, number>();
  const walk = (quad: number, k: number) => {
    let currentQuad = quad;
    let currentK = k;
    for (;;) {
      if (crossing.has(currentQuad)) return;
      crossing.set(currentQuad, currentK);
      const opposite = key(
        corner(net, currentQuad, currentK + 2),
        corner(net, currentQuad, currentK + 3),
      );
      const next = users.get(opposite)?.find((user) => user.quad !== currentQuad);
      if (!next) return;
      currentQuad = next.quad;
      currentK = next.k;
    }
  };
  for (const user of start) walk(user.quad, user.k);

  const base = net.vertices.length / 3;
  const middles = new Map<string, number>();
  const extra: number[] = [];
  const middle = (p: number, q: number): number => {
    const id = key(p, q);
    const existing = middles.get(id);
    if (existing !== undefined) return existing;
    const created = base + middles.size;
    middles.set(id, created);
    const [px, py, pz] = point(net, p);
    const [qx, qy, qz] = point(net, q);
    extra.push((px + qx) / 2, (py + qy) / 2, (pz + qz) / 2);
    return created;
  };
  const quads: number[] = [];
  for (let quad = 0; quad < quadCount(net); quad += 1) {
    const k = crossing.get(quad);
    if (k === undefined) {
      for (let i = 0; i < 4; i += 1) quads.push(corner(net, quad, i));
      continue;
    }
    // Rotated so the crossed edges are p0-p1 and p2-p3.
    const [p0, p1, p2, p3] = [0, 1, 2, 3].map((i) => corner(net, quad, k + i)) as [
      number,
      number,
      number,
      number,
    ];
    const m01 = middle(p0, p1);
    const m23 = middle(p2, p3);
    quads.push(p0, m01, m23, p3, m01, p1, p2, m23);
  }
  const vertices = new Float64Array(net.vertices.length + extra.length);
  vertices.set(net.vertices);
  vertices.set(extra, net.vertices.length);
  return {
    net: { vertices, quads: Uint32Array.from(quads) },
    added: Array.from({ length: middles.size }, (_, i) => base + i),
  };
}

const cross = (u: Vec3, v: Vec3): Vec3 => [
  u[1] * v[2] - u[2] * v[1],
  u[2] * v[0] - u[0] * v[2],
  u[0] * v[1] - u[1] * v[0],
];

function unit(v: Vec3): Vec3 {
  const length = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / length, v[1] / length, v[2] / length];
}

/**
 * The direction a border edge grows in: along the surface, away from its quad (the
 * quad lies left of a -> b seen from outside, along `normal`).
 */
export function edgeOutward(a: Vec3, b: Vec3, normal: Vec3): Vec3 {
  return unit(cross([b[0] - a[0], b[1] - a[1], b[2] - a[2]], normal));
}

/**
 * Per chain point the step of a new row of unit width: the mean outward direction of
 * its chain edges, lengthened at a corner (a mitre) so the new row keeps its width.
 */
export function outwardSteps(
  chain: readonly Edge[],
  pointOf: (vertex: number) => Vec3,
  normalOf: (vertex: number) => Vec3,
): Map<number, Vec3> {
  const directions = new Map<number, Vec3[]>();
  for (const { a, b } of chain) {
    const normal = unit(
      normalOf(a).map((value, axis) => value + (normalOf(b)[axis] ?? 0)) as unknown as Vec3,
    );
    const outward = edgeOutward(pointOf(a), pointOf(b), normal);
    for (const vertex of [a, b]) {
      const list = directions.get(vertex);
      if (list) list.push(outward);
      else directions.set(vertex, [outward]);
    }
  }
  const steps = new Map<number, Vec3>();
  for (const [vertex, list] of directions) {
    const sum = list.reduce<Vec3>(
      (total, d) => [total[0] + d[0], total[1] + d[1], total[2] + d[2]],
      [0, 0, 0],
    );
    const mean = unit(sum);
    // Mitre: the step keeps distance 1 from every edge it belongs to.
    const reach = Math.min(...list.map((d) => d[0] * mean[0] + d[1] * mean[1] + d[2] * mean[2]));
    const scale = 1 / Math.max(reach, 0.35);
    steps.set(vertex, [mean[0] * scale, mean[1] * scale, mean[2] * scale]);
  }
  return steps;
}

/**
 * The run of `loop` (a border chain in order) through `edge` whose edges are all kept,
 * wrapping round a closed loop: the sides of a border that face one way.
 */
export function keptRun(loop: readonly Edge[], kept: readonly boolean[], edge: Edge): Edge[] {
  const count = loop.length;
  const at = loop.findIndex((item) => item.a === edge.a && item.b === edge.b);
  if (at < 0 || !kept[at]) return [];
  if (kept.every(Boolean)) return [...loop];
  const closed = count > 2 && loop[0]?.a === loop[count - 1]?.b;
  // Back from the edge while kept (round the start of a closed loop), then forward.
  let first = at;
  for (let step = 1; step < count; step += 1) {
    const previous = first - 1;
    if (previous < 0 && !closed) break;
    if (!kept[(previous + count) % count]) break;
    first = previous;
  }
  const run: Edge[] = [];
  for (let i = first; run.length < count; i += 1) {
    if (i >= count && !closed) break;
    const index = ((i % count) + count) % count;
    if (!kept[index]) break;
    run.push(loop[index] as Edge);
  }
  return run;
}

/** Step length of a walk on the scan (mm). */
export const WALK_STEP_MM = 0.25;

export interface SurfacePoint {
  point: Vec3;
  normal: Vec3;
}

/**
 * The point `length` along a surface from `start`, setting out in `direction`: small
 * steps, each pulled back onto the surface, the heading kept tangent to it. Over a
 * rounded edge the walk follows the rounding and goes on down the wall, where a step
 * straight out would leave the surface and fall back onto the edge.
 */
export function walkOnSurface(
  start: Vec3,
  direction: Vec3,
  length: number,
  closest: (point: Vec3) => SurfacePoint | null,
  step = WALK_STEP_MM,
): Vec3 {
  let point = start;
  let heading = unit(direction);
  const count = Math.max(1, Math.ceil(length / step));
  const each = length / count;
  for (let i = 0; i < count; i += 1) {
    const ahead: Vec3 = [
      point[0] + heading[0] * each,
      point[1] + heading[1] * each,
      point[2] + heading[2] * each,
    ];
    const hit = closest(ahead);
    if (!hit) {
      point = ahead;
      continue;
    }
    const n = hit.normal;
    const tangent = (v: Vec3): Vec3 => {
      const along = v[0] * n[0] + v[1] * n[1] + v[2] * n[2];
      return [v[0] - along * n[0], v[1] - along * n[1], v[2] - along * n[2]];
    };
    let onward = tangent([
      hit.point[0] - point[0],
      hit.point[1] - point[1],
      hit.point[2] - point[2],
    ]);
    if (Math.hypot(onward[0], onward[1], onward[2]) < 1e-9) onward = tangent(heading);
    heading = unit(onward);
    point = hit.point;
  }
  return point;
}

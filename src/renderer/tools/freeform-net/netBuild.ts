// Building a net by hand, as in QuickSurface: a face from four clicked points, a new
// row of faces dragged out of border edges (its points dropped onto the scan or onto
// points of the net, which joins pieces), a new loop through a ring of faces (S), and
// two points welded into one. Every operation keeps the net made of quads, oriented
// alike, so its rows stay aligned and its surface stays smooth.

import type { Vec3 } from '../../viewport/api';
import type { Net } from './netModel';
import { type Edge, corner, edgeKey, edgeQuads, quadCount } from './netTopology';

function point(net: Net, vertex: number): Vec3 {
  return [
    net.vertices[vertex * 3] ?? 0,
    net.vertices[vertex * 3 + 1] ?? 0,
    net.vertices[vertex * 3 + 2] ?? 0,
  ];
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

/** Where a new row point goes: a new point there, or an existing point it joins. */
export type RowTarget = Vec3 | { onto: number };

/** The target is an existing point (a join), not a position. */
export const joinsPoint = (target: RowTarget): target is { onto: number } => !Array.isArray(target);

/**
 * A new row of quads along border edges (consecutive, as `borderChain` gives them):
 * every chain point gets a new point at its target, or joins an existing point (a row
 * dropped onto another piece of the net bridges the gap), and every edge a quad
 * between them, oriented like its neighbour. A quad that would collapse (two corners
 * joined into one point) is left out. Returns the net, the new points and the edges
 * along the outside of the row (directed as in their quads).
 */
export function extrudeEdges(
  net: Net,
  chain: readonly Edge[],
  targets: (vertex: number) => RowTarget,
): { net: Net; added: number[]; outer: Edge[] } {
  const points: number[] = [];
  chain.forEach((edge, i) => {
    if (i === 0) points.push(edge.a);
    points.push(edge.b);
  });
  const closed = points.length > 2 && points[0] === points[points.length - 1];
  if (closed) points.pop();
  const base = net.vertices.length / 3;
  const copy = new Map<number, number>();
  const created: Vec3[] = [];
  for (const vertex of points) {
    const target = targets(vertex);
    if (joinsPoint(target)) copy.set(vertex, target.onto);
    else {
      copy.set(vertex, base + created.length);
      created.push(target);
    }
  }
  const vertices = new Float64Array((base + created.length) * 3);
  vertices.set(net.vertices);
  created.forEach((position, i) => vertices.set(position, (base + i) * 3));
  // The neighbour runs a -> b, so the new quad runs b -> a -> a' -> b' (outer edge a' -> b').
  const rows = chain
    .map(({ a, b }) => [b, a, copy.get(a) ?? a, copy.get(b) ?? b])
    .filter((quad) => new Set(quad).size === 4);
  const quads = new Uint32Array(net.quads.length + rows.length * 4);
  quads.set(net.quads);
  rows.forEach((quad, i) => quads.set(quad, net.quads.length + i * 4));
  return {
    net: { vertices, quads },
    added: created.map((_, i) => base + i),
    outer: rows.map(([, , a, b]) => ({ a: a ?? 0, b: b ?? 0 })),
  };
}

/**
 * The net with point `from` welded onto point `into` (which keeps its place), or null
 * when that would break the net: both in one quad, or an edge then used by more than
 * two quads or twice in one direction (opposite orientations).
 */
export function mergePoints(net: Net, from: number, into: number): Net | null {
  if (from === into) return null;
  const renamed = Uint32Array.from(net.quads, (vertex) => (vertex === from ? into : vertex));
  const directed = new Set<string>();
  const uses = new Map<string, number>();
  for (let quad = 0; quad < renamed.length / 4; quad += 1) {
    const corners = renamed.subarray(quad * 4, quad * 4 + 4);
    if (new Set(corners).size < 4) return null;
    for (let k = 0; k < 4; k += 1) {
      const [p, q] = [corners[k] ?? 0, corners[(k + 1) % 4] ?? 0];
      if (directed.has(`${p}>${q}`)) return null;
      directed.add(`${p}>${q}`);
      const id = edgeKey(p, q);
      uses.set(id, (uses.get(id) ?? 0) + 1);
      if ((uses.get(id) ?? 0) > 2) return null;
    }
  }
  // Drop the point `from`; later points move down by one.
  const quads = Uint32Array.from(renamed, (vertex) => (vertex > from ? vertex - 1 : vertex));
  const vertices = new Float64Array(net.vertices.length - 3);
  vertices.set(net.vertices.subarray(0, from * 3));
  vertices.set(net.vertices.subarray(from * 3 + 3), from * 3);
  return { vertices, quads };
}

/**
 * A new loop through the ring of quads that cross the edge a-b: every crossed edge
 * gets its midpoint, and every quad of the ring becomes two. Returns the net and the
 * new points (empty if a-b is no edge).
 */
export function splitRing(net: Net, a: number, b: number): { net: Net; added: number[] } {
  const users = edgeQuads(net);
  const start = users.get(edgeKey(a, b));
  if (!start) return { net, added: [] };
  // Walk across the ring in both directions from the edge.
  const crossing = new Map<number, number>();
  const walk = (quad: number, k: number) => {
    let currentQuad = quad;
    let currentK = k;
    for (;;) {
      if (crossing.has(currentQuad)) return;
      crossing.set(currentQuad, currentK);
      const opposite = edgeKey(
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
    const id = edgeKey(p, q);
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

/**
 * The net without the quads `drop` picks (by their corners) and without the points no
 * quad uses any more; null if nothing or everything would be removed.
 */
export function removeQuads(net: Net, drop: (corners: number[]) => boolean): Net | null {
  const kept: number[] = [];
  for (let quad = 0; quad < quadCount(net); quad += 1) {
    const corners = [0, 1, 2, 3].map((k) => corner(net, quad, k));
    if (!drop(corners)) kept.push(...corners);
  }
  if (kept.length === 0 || kept.length === net.quads.length) return null;
  // Remaining points keep their order, so their numbers only shift down.
  const used = [...new Set(kept)].sort((a, b) => a - b);
  const index = new Map(used.map((vertex, i) => [vertex, i]));
  const vertices = new Float64Array(used.length * 3);
  used.forEach((vertex, i) => vertices.set(point(net, vertex), i * 3));
  return { vertices, quads: Uint32Array.from(kept, (vertex) => index.get(vertex) ?? 0) };
}

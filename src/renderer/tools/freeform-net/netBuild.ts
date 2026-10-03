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
 * the net's corners (border points with one quad) or all the way round a closed border.
 */
export function borderChain(net: Net, edge: Edge): Edge[] {
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
  const passes = (vertex: number) => (quadsAt.get(vertex) ?? 0) === 2;
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

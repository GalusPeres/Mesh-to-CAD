// Reading a net's structure: its edges and the quads using them, its open border,
// the border chains and runs a drag grows rows on, and the edge loop a double click
// selects. Nothing here changes the net (netBuild does).

import type { Net } from './netModel';

/** An edge of a quad, directed as in that quad (counter-clockwise seen from outside). */
export interface Edge {
  a: number;
  b: number;
}

/** The same key for a-b and b-a. */
export const edgeKey = (a: number, b: number): string => (a < b ? `${a},${b}` : `${b},${a}`);

export function quadCount(net: Net): number {
  return net.quads.length / 4;
}

export function corner(net: Net, quad: number, k: number): number {
  return net.quads[quad * 4 + (k % 4)] ?? 0;
}

/** Quads (and the edge's position k in each) by undirected edge. */
export function edgeQuads(net: Net): Map<string, { quad: number; k: number }[]> {
  const result = new Map<string, { quad: number; k: number }[]>();
  for (let quad = 0; quad < quadCount(net); quad += 1) {
    for (let k = 0; k < 4; k += 1) {
      const id = edgeKey(corner(net, quad, k), corner(net, quad, k + 1));
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
  const seen = new Set([edgeKey(edge.a, edge.b)]);
  for (let current = edge; passes(current.b);) {
    const next = starting.get(current.b);
    if (!next || seen.has(edgeKey(next.a, next.b))) break;
    seen.add(edgeKey(next.a, next.b));
    chain.push(next);
    current = next;
  }
  for (let current = edge; passes(current.a);) {
    const previous = ending.get(current.a);
    if (!previous || seen.has(edgeKey(previous.a, previous.b))) break;
    seen.add(edgeKey(previous.a, previous.b));
    chain.unshift(previous);
    current = previous;
  }
  return chain;
}

/**
 * Chosen border edges as runs of consecutive edges, each directed as in its quad and
 * in border order (a chosen closed loop is one run). Edges that are no border are left out.
 */
export function borderRuns(net: Net, chosen: readonly Edge[]): Edge[][] {
  const wanted = new Set(chosen.map((edge) => edgeKey(edge.a, edge.b)));
  const edges = borderEdges(net).filter((edge) => wanted.has(edgeKey(edge.a, edge.b)));
  const starting = new Map<number, Edge>();
  const ending = new Map<number, Edge>();
  for (const edge of edges) {
    starting.set(edge.a, edge);
    ending.set(edge.b, edge);
  }
  const used = new Set<string>();
  const runs: Edge[][] = [];
  for (const edge of edges) {
    if (used.has(edgeKey(edge.a, edge.b))) continue;
    let first = edge;
    for (let step = 0; step < edges.length; step += 1) {
      const previous = ending.get(first.a);
      if (!previous || previous === edge) break;
      first = previous;
    }
    const run: Edge[] = [];
    for (let current: Edge | undefined = first; current; current = starting.get(current.b)) {
      if (used.has(edgeKey(current.a, current.b))) break;
      used.add(edgeKey(current.a, current.b));
      run.push(current);
    }
    runs.push(run);
  }
  return runs;
}

/**
 * The chain a double click on an edge selects: for a border edge its border up to the
 * net's corners; otherwise the edge loop straight through regular points (four quads),
 * up to the border or an irregular point.
 */
export function edgeLoop(net: Net, edge: Edge): Edge[] {
  const users = edgeQuads(net);
  if ((users.get(edgeKey(edge.a, edge.b))?.length ?? 0) < 2) return borderChain(net, edge);
  const neighbours = new Map<number, Set<number>>();
  const quadsAt = new Map<number, number>();
  for (let quad = 0; quad < quadCount(net); quad += 1) {
    for (let k = 0; k < 4; k += 1) {
      const [p, q] = [corner(net, quad, k), corner(net, quad, k + 1)];
      quadsAt.set(p, (quadsAt.get(p) ?? 0) + 1);
      for (const [from, to] of [
        [p, q],
        [q, p],
      ] as const) {
        const set = neighbours.get(from);
        if (set) set.add(to);
        else neighbours.set(from, new Set([to]));
      }
    }
  }
  const border = new Set(borderEdges(net).flatMap(({ a, b }) => [a, b]));
  // Past a regular inner point the loop goes on to the one neighbour that shares no
  // quad with the edge it came along.
  const across = (from: number, at: number): number | null => {
    if (border.has(at) || quadsAt.get(at) !== 4) return null;
    const beside = new Set<number>();
    for (const { quad } of users.get(edgeKey(from, at)) ?? [])
      for (let k = 0; k < 4; k += 1) beside.add(corner(net, quad, k));
    const ahead = [...(neighbours.get(at) ?? [])].filter((vertex) => !beside.has(vertex));
    return ahead.length === 1 ? (ahead[0] ?? null) : null;
  };
  const chain: Edge[] = [edge];
  const seen = new Set([edgeKey(edge.a, edge.b)]);
  const walk = (start: number, end: number, forward: boolean) => {
    let [from, at] = [start, end];
    for (
      let to = across(from, at);
      to !== null && !seen.has(edgeKey(at, to));
      to = across(from, at)
    ) {
      seen.add(edgeKey(at, to));
      if (forward) chain.push({ a: at, b: to });
      else chain.unshift({ a: to, b: at });
      [from, at] = [at, to];
    }
  };
  walk(edge.a, edge.b, true);
  walk(edge.b, edge.a, false);
  return chain;
}

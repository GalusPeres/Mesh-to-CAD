// The net being edited (control points and quads), its draft history, and the
// solve that turns wanted moves of surface points into moves of control points.

import type { LimitSurface } from './limitSurface';

export interface Net {
  /** x, y, z per control point, part coordinates. */
  vertices: Float64Array;
  /** Four control-point indices per quad, counter-clockwise seen from outside. */
  quads: Uint32Array;
}

export function cloneNet(net: Net): Net {
  return { vertices: net.vertices.slice(), quads: net.quads.slice() };
}

export function sameTopology(a: Net, b: Net): boolean {
  if (a.vertices.length !== b.vertices.length || a.quads.length !== b.quads.length) return false;
  for (let i = 0; i < a.quads.length; i += 1) if (a.quads[i] !== b.quads[i]) return false;
  return true;
}

/** Undo and redo of the draft net, independent of the document history. */
export class NetHistory {
  private entries: Net[] = [];
  private position = -1;

  constructor(private readonly limit = 100) {}

  get canUndo(): boolean {
    return this.position > 0;
  }

  get canRedo(): boolean {
    return this.position < this.entries.length - 1;
  }

  reset(net: Net | null): void {
    this.entries = net ? [cloneNet(net)] : [];
    this.position = this.entries.length - 1;
  }

  /** Record a new state; redo steps after the current one are dropped. */
  push(net: Net): void {
    this.entries = this.entries.slice(0, this.position + 1);
    this.entries.push(cloneNet(net));
    if (this.entries.length > this.limit) this.entries.shift();
    this.position = this.entries.length - 1;
  }

  undo(): Net | null {
    if (!this.canUndo) return null;
    this.position -= 1;
    return cloneNet(this.entries[this.position] as Net);
  }

  redo(): Net | null {
    if (!this.canRedo) return null;
    this.position += 1;
    return cloneNet(this.entries[this.position] as Net);
  }
}

const SOLVE_ITERATIONS = 12;

/**
 * Control-point offsets that move the limit points of `controls` by `wanted`
 * (x, y, z per entry). The limit point of a control point is a weighted average of
 * it and its neighbours, so moving one point by d moves its limit point by w d
 * (w about 0.44 on a regular net) and moving a whole patch by d moves its inside
 * by d. Gauss-Seidel on the limit rows restricted to the moved points covers both;
 * the restricted matrix is symmetric positive definite, so it converges.
 */
export function controlOffsets(
  surface: LimitSurface,
  controls: Uint32Array,
  wanted: Float64Array,
): Float64Array {
  const { rows, columns, weights } = surface.map;
  const slot = new Map<number, number>();
  controls.forEach((control, index) => slot.set(control, index));
  const offsets = new Float64Array(controls.length * 3);
  const own = Float64Array.from(controls, (control) => surface.ownWeight(control) || 1);
  for (let iteration = 0; iteration < SOLVE_ITERATIONS; iteration += 1) {
    controls.forEach((control, index) => {
      let x = 0;
      let y = 0;
      let z = 0;
      for (let k = rows[control] ?? 0; k < (rows[control + 1] ?? 0); k += 1) {
        const other = slot.get(columns[k] ?? -1);
        if (other === undefined) continue;
        const weight = weights[k] ?? 0;
        x += weight * (offsets[other * 3] ?? 0);
        y += weight * (offsets[other * 3 + 1] ?? 0);
        z += weight * (offsets[other * 3 + 2] ?? 0);
      }
      const o = index * 3;
      const scale = 1 / (own[index] ?? 1);
      offsets[o] = (offsets[o] ?? 0) + ((wanted[o] ?? 0) - x) * scale;
      offsets[o + 1] = (offsets[o + 1] ?? 0) + ((wanted[o + 1] ?? 0) - y) * scale;
      offsets[o + 2] = (offsets[o + 2] ?? 0) + ((wanted[o + 2] ?? 0) - z) * scale;
    });
  }
  return offsets;
}

/** Number of control points with a valence other than 4 inside the net (irregular points). */
export function irregularCount(
  edges: Uint32Array,
  boundaryEdges: Uint8Array,
  controlCount: number,
): number {
  const valence = new Uint16Array(controlCount);
  const onBorder = new Uint8Array(controlCount);
  for (let e = 0; e < edges.length / 2; e += 1) {
    const a = edges[e * 2] ?? 0;
    const b = edges[e * 2 + 1] ?? 0;
    valence[a] = (valence[a] ?? 0) + 1;
    valence[b] = (valence[b] ?? 0) + 1;
    if (boundaryEdges[e]) {
      onBorder[a] = 1;
      onBorder[b] = 1;
    }
  }
  let count = 0;
  for (let i = 0; i < controlCount; i += 1) if (!onBorder[i] && valence[i] !== 4) count += 1;
  return count;
}

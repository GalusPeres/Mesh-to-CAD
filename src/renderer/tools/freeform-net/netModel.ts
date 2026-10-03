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

/** A draft history step: the net and its pinned control points. */
export interface NetStep {
  net: Net;
  pinned: readonly number[];
}

function cloneStep(step: NetStep): NetStep {
  return { net: cloneNet(step.net), pinned: [...step.pinned] };
}

/** Undo and redo of the draft net, independent of the document history. */
export class NetHistory {
  private entries: NetStep[] = [];
  private position = -1;

  constructor(private readonly limit = 100) {}

  get canUndo(): boolean {
    return this.position > 0;
  }

  get canRedo(): boolean {
    return this.position < this.entries.length - 1;
  }

  reset(net: Net | null, pinned: readonly number[] = []): void {
    this.entries = net ? [cloneStep({ net, pinned })] : [];
    this.position = this.entries.length - 1;
  }

  /** Record a new state; redo steps after the current one are dropped. */
  push(net: Net, pinned: readonly number[] = []): void {
    this.entries = this.entries.slice(0, this.position + 1);
    this.entries.push(cloneStep({ net, pinned }));
    if (this.entries.length > this.limit) this.entries.shift();
    this.position = this.entries.length - 1;
  }

  undo(): NetStep | null {
    if (!this.canUndo) return null;
    this.position -= 1;
    return cloneStep(this.entries[this.position] as NetStep);
  }

  redo(): NetStep | null {
    if (!this.canRedo) return null;
    this.position += 1;
    return cloneStep(this.entries[this.position] as NetStep);
  }
}

/** Enough for the rings a drag holds still; the restricted system is well conditioned. */
const SOLVE_ITERATIONS = 40;

/**
 * Control-point offsets that move the limit points of `controls` by `wanted`
 * (x, y, z per entry; zero holds a limit point still). The limit point of a control
 * point is a weighted average of it and its neighbours, so moving one point by d moves
 * its limit point by w d (w about 0.44 on a regular net) and moving a whole patch by d
 * moves its inside by d. Gauss-Seidel on the limit rows restricted to the moved points
 * covers both; the restricted matrix is symmetric positive definite, so it converges.
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
  const goal = wanted.reduce((largest, value) => Math.max(largest, Math.abs(value)), 0);
  for (let iteration = 0; iteration < SOLVE_ITERATIONS; iteration += 1) {
    let step = 0;
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
      const residual = [(wanted[o] ?? 0) - x, (wanted[o + 1] ?? 0) - y, (wanted[o + 2] ?? 0) - z];
      residual.forEach((value, axis) => {
        offsets[o + axis] = (offsets[o + axis] ?? 0) + value * scale;
        step = Math.max(step, Math.abs(value));
      });
    });
    if (step <= goal * 1e-9) break;
  }
  return offsets;
}

/** Control points inside the net whose valence is not 4 (irregular points). */
export function irregularPoints(
  edges: Uint32Array,
  boundaryEdges: Uint8Array,
  controlCount: number,
): number[] {
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
  const irregular: number[] = [];
  for (let i = 0; i < controlCount; i += 1) if (!onBorder[i] && valence[i] !== 4) irregular.push(i);
  return irregular;
}

export interface Plane {
  origin: [number, number, number];
  normal: [number, number, number];
}

/** Eigenvalues and eigenvectors (columns) of a symmetric 3 x 3 matrix, by Jacobi rotations. */
function symmetricEigen(m: number[][]): { values: number[]; vectors: number[][] } {
  const a = m.map((row) => row.slice());
  const v = [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ];
  for (let sweep = 0; sweep < 50; sweep += 1) {
    let off = 0;
    for (let p = 0; p < 3; p += 1) for (let q = p + 1; q < 3; q += 1) off += a[p]![q]! ** 2;
    if (off < 1e-30) break;
    for (let p = 0; p < 3; p += 1) {
      for (let q = p + 1; q < 3; q += 1) {
        const apq = a[p]![q]!;
        if (Math.abs(apq) < 1e-300) continue;
        const theta = (a[q]![q]! - a[p]![p]!) / (2 * apq);
        const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
        const c = 1 / Math.sqrt(t * t + 1);
        const s = t * c;
        for (let k = 0; k < 3; k += 1) {
          const akp = a[k]![p]!;
          const akq = a[k]![q]!;
          a[k]![p] = c * akp - s * akq;
          a[k]![q] = s * akp + c * akq;
        }
        for (let k = 0; k < 3; k += 1) {
          const apk = a[p]![k]!;
          const aqk = a[q]![k]!;
          a[p]![k] = c * apk - s * aqk;
          a[q]![k] = s * apk + c * aqk;
        }
        for (let k = 0; k < 3; k += 1) {
          const vkp = v[k]![p]!;
          const vkq = v[k]![q]!;
          v[k]![p] = c * vkp - s * vkq;
          v[k]![q] = s * vkp + c * vkq;
        }
      }
    }
  }
  return { values: [a[0]![0]!, a[1]![1]!, a[2]![2]!], vectors: v };
}

/** Least-squares plane through points (x, y, z triples); null for fewer than three. */
export function fitPlane(points: Float64Array): Plane | null {
  const count = points.length / 3;
  if (count < 3) return null;
  const centre: [number, number, number] = [0, 0, 0];
  for (let i = 0; i < count; i += 1)
    for (let axis = 0; axis < 3; axis += 1) centre[axis]! += points[i * 3 + axis]! / count;
  const covariance = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ];
  for (let i = 0; i < count; i += 1) {
    const d = [0, 1, 2].map((axis) => points[i * 3 + axis]! - centre[axis]!);
    for (let r = 0; r < 3; r += 1)
      for (let c = 0; c < 3; c += 1) covariance[r]![c]! += d[r]! * d[c]!;
  }
  const { values, vectors } = symmetricEigen(covariance);
  const smallest = values.indexOf(Math.min(...values));
  const normal: [number, number, number] = [
    vectors[0]![smallest]!,
    vectors[1]![smallest]!,
    vectors[2]![smallest]!,
  ];
  const length = Math.hypot(...normal) || 1;
  return { origin: centre, normal: [normal[0] / length, normal[1] / length, normal[2] / length] };
}

/** Move the given control points onto the plane (perpendicular projection), in place. */
export function projectOntoPlane(
  vertices: Float64Array,
  controls: Iterable<number>,
  plane: Plane,
): void {
  const [ox, oy, oz] = plane.origin;
  const [nx, ny, nz] = plane.normal;
  for (const control of controls) {
    const o = control * 3;
    const distance =
      (vertices[o]! - ox) * nx + (vertices[o + 1]! - oy) * ny + (vertices[o + 2]! - oz) * nz;
    vertices[o] = vertices[o]! - distance * nx;
    vertices[o + 1] = vertices[o + 1]! - distance * ny;
    vertices[o + 2] = vertices[o + 2]! - distance * nz;
  }
}

// The net's limit surface as a dense mesh. Its vertex positions are a fixed sparse
// linear map of the control points (kernel `net.limitMap`, depending only on the
// quads), so a dragged control point re-evaluates just the rows it influences.

import type { LimitMapResult } from '@shared/protocol/generated/net';

export class LimitSurface {
  /** x, y, z per dense vertex; vertex i < controlCount is the limit of control point i. */
  readonly positions: Float32Array;
  readonly fineCount: number;
  private readonly rows: Uint32Array;
  private readonly columns: Uint32Array;
  private readonly weights: Float32Array;
  /** Transposed structure: the dense rows that read each control point. */
  private readonly readersStart: Uint32Array;
  private readonly readers: Uint32Array;
  private readonly stamp: Uint32Array;
  private stampValue = 0;

  constructor(
    readonly map: LimitMapResult,
    readonly controlCount: number,
  ) {
    this.fineCount = map.fineCount;
    this.rows = map.rows;
    this.columns = map.columns;
    this.weights = map.weights;
    this.positions = new Float32Array(this.fineCount * 3);
    const counts = new Uint32Array(controlCount + 1);
    for (const column of this.columns) counts[column + 1] = (counts[column + 1] ?? 0) + 1;
    for (let c = 0; c < controlCount; c += 1)
      counts[c + 1] = (counts[c + 1] ?? 0) + (counts[c] ?? 0);
    this.readersStart = counts;
    this.readers = new Uint32Array(this.columns.length);
    const fill = counts.slice(0, controlCount);
    for (let row = 0; row < this.fineCount; row += 1) {
      for (let k = this.rows[row] ?? 0; k < (this.rows[row + 1] ?? 0); k += 1) {
        const column = this.columns[k] ?? 0;
        this.readers[fill[column] ?? 0] = row;
        fill[column] = (fill[column] ?? 0) + 1;
      }
    }
    this.stamp = new Uint32Array(this.fineCount);
  }

  /** Recompute every dense vertex. */
  evaluate(control: Float64Array): void {
    for (let row = 0; row < this.fineCount; row += 1) this.evaluateRow(control, row);
  }

  /** Recompute the given dense vertices. */
  evaluateRows(control: Float64Array, rows: Uint32Array): void {
    for (const row of rows) this.evaluateRow(control, row);
  }

  /** The dense vertices that depend on any of the control points, each once. */
  rowsOf(controls: Iterable<number>): Uint32Array {
    this.stampValue += 1;
    if (this.stampValue === 0xffffffff) {
      this.stamp.fill(0);
      this.stampValue = 1;
    }
    const result: number[] = [];
    for (const control of controls) {
      const end = this.readersStart[control + 1] ?? 0;
      for (let k = this.readersStart[control] ?? 0; k < end; k += 1) {
        const row = this.readers[k] ?? 0;
        if (this.stamp[row] === this.stampValue) continue;
        this.stamp[row] = this.stampValue;
        result.push(row);
      }
    }
    return Uint32Array.from(result);
  }

  /** Weight of control point i in its own limit position (dense vertex i). */
  ownWeight(control: number): number {
    for (let k = this.rows[control] ?? 0; k < (this.rows[control + 1] ?? 0); k += 1) {
      if (this.columns[k] === control) return this.weights[k] ?? 0;
    }
    return 0;
  }

  /** Limit position of control point i (dense vertex i). */
  limitPoint(control: number): [number, number, number] {
    const o = control * 3;
    return [this.positions[o] ?? 0, this.positions[o + 1] ?? 0, this.positions[o + 2] ?? 0];
  }

  private evaluateRow(control: Float64Array, row: number): void {
    let x = 0;
    let y = 0;
    let z = 0;
    for (let k = this.rows[row] ?? 0; k < (this.rows[row + 1] ?? 0); k += 1) {
      const weight = this.weights[k] ?? 0;
      const c = (this.columns[k] ?? 0) * 3;
      x += weight * (control[c] ?? 0);
      y += weight * (control[c + 1] ?? 0);
      z += weight * (control[c + 2] ?? 0);
    }
    const o = row * 3;
    this.positions[o] = x;
    this.positions[o + 1] = y;
    this.positions[o + 2] = z;
  }
}

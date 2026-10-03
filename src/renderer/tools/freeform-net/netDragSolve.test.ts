import { describe, expect, it } from 'vitest';

import { gridFixture } from './gridFixture';
import { LimitSurface } from './limitSurface';
import { dragOffsets, dragSet } from './netDragSolve';

const N = 15;
const C = 7;

/** Drag the limit point of the centre point up by 1; the dense z values before and after. */
function dragCentre(options: { keepNeighbours: boolean; pinned?: number[]; chosen?: number[] }) {
  const grid = gridFixture(N);
  const surface = new LimitSurface(grid.map, N * N);
  const vertices = grid.net.vertices.slice();
  surface.evaluate(vertices);
  const before = surface.positions.slice();
  const set = dragSet(
    surface,
    options.chosen ?? [grid.id(C, C)],
    new Set(options.pinned ?? []),
    options.keepNeighbours,
  );
  const moves = new Float64Array(set.dragged * 3);
  for (let k = 0; k < set.dragged; k += 1) moves[k * 3 + 2] = 1;
  const offsets = dragOffsets(surface, set, moves);
  set.controls.forEach((control, index) => {
    for (let axis = 0; axis < 3; axis += 1)
      vertices[control * 3 + axis]! += offsets[index * 3 + axis]!;
  });
  surface.evaluate(vertices);
  const lift = (row: number) => surface.positions[row * 3 + 2]! - before[row * 3 + 2]!;
  return { grid, set, lift };
}

/** Largest lift of the dense vertices whose grid position passes `where`. */
function largest(
  result: ReturnType<typeof dragCentre>,
  where: (x: number, y: number) => boolean,
): number {
  let max = 0;
  result.grid.at.forEach(([x, y], row) => {
    if (where(x - C, y - C)) max = Math.max(max, Math.abs(result.lift(row)));
  });
  return max;
}

const ring = (x: number, y: number) => Math.max(Math.abs(x), Math.abs(y));
const neighbours = [-1, 0, 1].flatMap((i) =>
  [-1, 0, 1].filter((j) => i !== 0 || j !== 0).map((j) => [C + i, C + j] as const),
);

describe('dragging a point', () => {
  it('pulls the neighbouring points along by default', () => {
    const plain = dragCentre({ keepNeighbours: false });
    expect(plain.lift(plain.grid.id(C, C))).toBeCloseTo(1, 5);
    expect(plain.lift(plain.grid.id(C + 1, C))).toBeCloseTo(0.25, 3);
    expect(plain.set.controls).toEqual(Uint32Array.from([plain.grid.id(C, C)]));
  });

  it("with Don't move neighbours, holds the neighbours' points and bends only its own quads", () => {
    const held = dragCentre({ keepNeighbours: true });
    const { id } = held.grid;
    expect(held.lift(id(C, C))).toBeCloseTo(1, 5);
    for (const [i, j] of neighbours) expect(Math.abs(held.lift(id(i, j)))).toBeLessThan(1e-5);
    // The dragged point and its eight neighbours are solved together.
    expect(held.set.dragged).toBe(1);
    expect(held.set.controls.length).toBe(9);
    // Inside its own quads the surface rises; beyond the neighbours it only eases out
    // (C2 continuity forbids a sharp stop) and three rings out it is untouched.
    expect(largest(held, (x, y) => ring(x, y) <= 0.5)).toBeGreaterThan(0.6);
    expect(largest(held, (x, y) => ring(x, y) > 1)).toBeLessThan(0.18);
    expect(largest(held, (x, y) => ring(x, y) > 2)).toBeLessThan(0.035);
    expect(largest(held, (x, y) => ring(x, y) >= 3)).toBeLessThan(1e-6);
  });

  it('holds pinned points, also behind held neighbours', () => {
    const { id } = gridFixture(N);
    const pinned = [id(C + 1, C), id(C + 2, C), id(C - 2, C + 1)];
    for (const keepNeighbours of [false, true]) {
      const result = dragCentre({ keepNeighbours, pinned });
      expect(result.lift(id(C, C))).toBeCloseTo(1, 5);
      for (const control of pinned) expect(Math.abs(result.lift(control))).toBeLessThan(1e-5);
    }
  });

  it('never drags pinned points, even when they are chosen', () => {
    const grid = gridFixture(N);
    const surface = new LimitSurface(grid.map, N * N);
    const pinned = new Set([grid.id(C, C)]);
    expect(dragSet(surface, [grid.id(C, C)], pinned, false).dragged).toBe(0);
    const mixed = dragSet(surface, [grid.id(C, C), grid.id(C, C + 3)], pinned, false);
    expect(mixed.dragged).toBe(1);
    expect(mixed.controls[0]).toBe(grid.id(C, C + 3));
  });

  it('moves a chosen patch as a whole', () => {
    const { id } = gridFixture(N);
    const chosen = [-1, 0, 1].flatMap((i) => [-1, 0, 1].map((j) => id(C + i, C + j)));
    const result = dragCentre({ keepNeighbours: false, chosen });
    for (const control of chosen) expect(result.lift(control)).toBeCloseTo(1, 5);
  });
});

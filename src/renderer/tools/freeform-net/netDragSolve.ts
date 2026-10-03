// Which control points a drag moves, and by how much. The dragged points' limit points
// follow the pointer. Pinned limit points hold still, and with "Don't move neighbours"
// (QuickSurface, Free Form Basics) so do the limit points the dragged control points
// influence: those control points are solved together with the dragged ones, so the
// neighbours' points stay where they are and the bulge stays within the dragged
// points' own quads (beyond them the surface only eases out, as it must to stay smooth).
// The same solve puts pinned and dropped points exactly where they belong.

import type { LimitSurface } from './limitSurface';
import { controlOffsets } from './netModel';

export interface DragSet {
  /** The dragged control points first, then the ones solved to hold their limit points. */
  controls: Uint32Array;
  /** How many of `controls` are dragged. */
  dragged: number;
}

/** The control points of a drag of the chosen points (pinned ones are not dragged). */
export function dragSet(
  surface: LimitSurface,
  chosen: Iterable<number>,
  pinned: ReadonlySet<number>,
  keepNeighbours: boolean,
): DragSet {
  const order: number[] = [];
  const known = new Set<number>();
  const add = (control: number) => {
    if (known.has(control)) return;
    known.add(control);
    order.push(control);
  };
  for (const control of chosen) if (!pinned.has(control)) add(control);
  const dragged = order.length;
  if (keepNeighbours)
    for (let i = 0; i < dragged; i += 1)
      for (const reader of surface.limitReaders(order[i] ?? 0)) add(reader);
  // A held control point moves too, so the pinned points it influences are held as well.
  for (let i = 0; i < order.length; i += 1)
    for (const reader of surface.limitReaders(order[i] ?? 0)) if (pinned.has(reader)) add(reader);
  return { controls: Uint32Array.from(order), dragged };
}

/**
 * Control-point offsets of the whole set for moves of the dragged limit points (x, y, z
 * per dragged point); every other limit point of the set stays.
 */
export function dragOffsets(
  surface: LimitSurface,
  set: DragSet,
  moves: Float64Array,
): Float64Array {
  const wanted = new Float64Array(set.controls.length * 3);
  wanted.set(moves.subarray(0, set.dragged * 3));
  return controlOffsets(surface, set.controls, wanted);
}

/** The limit points of the given control points (x, y, z each, in their order). */
export function limitsOf(surface: LimitSurface, controls: readonly number[]): Float64Array {
  const limits = new Float64Array(controls.length * 3);
  controls.forEach((control, index) => limits.set(surface.limitPoint(control), index * 3));
  return limits;
}

/**
 * Move the given control points, and only them, so that their limit points are at
 * `targets` (x, y, z each), in place; `surface` must show `vertices` and is updated.
 */
export function placeLimits(
  surface: LimitSurface,
  vertices: Float64Array,
  controls: readonly number[],
  targets: Float64Array,
): void {
  if (controls.length === 0) return;
  const set = Uint32Array.from(controls);
  const current = limitsOf(surface, controls);
  const offsets = controlOffsets(
    surface,
    set,
    targets.map((target, i) => target - (current[i] ?? 0)),
  );
  set.forEach((control, index) => {
    for (let axis = 0; axis < 3; axis += 1)
      vertices[control * 3 + axis] =
        (vertices[control * 3 + axis] ?? 0) + (offsets[index * 3 + axis] ?? 0);
  });
  surface.evaluateRows(vertices, surface.rowsOf(set));
}

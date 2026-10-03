// Pinned points of the net: chosen points that dragging, Snap to scan, Smooth and Q
// leave where they are. What stays is the point the user sees, the limit point: kernel
// fits hold the pinned control points (`fixed`), and a small solve afterwards moves
// only pinned control points so that their limit points return exactly (a pinned point
// next to moved ones would otherwise follow them a little).

import type { LimitSurface } from './limitSurface';
import { type Net, controlOffsets } from './netModel';

/** Pin (or release) the given control points; true if the pinned set changed. */
export function applyPins(pinned: Set<number>, controls: Iterable<number>, pin: boolean): boolean {
  const before = pinned.size;
  for (const control of controls) {
    if (pin) pinned.add(control);
    else pinned.delete(control);
  }
  return pinned.size !== before;
}

/**
 * The kernel's `fixed` mask: pinned points, and with chosen points everything else as
 * well (only the chosen ones are fitted); null when every point may move.
 */
export function fixedMask(
  count: number,
  pinned: ReadonlySet<number>,
  chosen: ReadonlySet<number>,
): Uint8Array | null {
  if (pinned.size === 0 && chosen.size === 0) return null;
  return Uint8Array.from({ length: count }, (_, i) =>
    pinned.has(i) || (chosen.size > 0 && !chosen.has(i)) ? 1 : 0,
  );
}

/**
 * The pins of `old` in the numbering of `next`. Fits and most edits keep the numbers
 * (edits append new points); welding and deleting drop points and renumber the rest
 * without moving them, so there a pin follows its control point's exact position. In
 * the order given; null where the point is gone.
 */
export function carryPins(old: Net, next: Net, pinned: Iterable<number>): (number | null)[] {
  if (next.vertices.length >= old.vertices.length) return [...pinned];
  const key = (vertices: Float64Array, i: number) =>
    `${vertices[i * 3]},${vertices[i * 3 + 1]},${vertices[i * 3 + 2]}`;
  const byPosition = new Map<string, number>();
  for (let i = 0; i < next.vertices.length / 3; i += 1) byPosition.set(key(next.vertices, i), i);
  return [...pinned].map((control) => byPosition.get(key(old.vertices, control)) ?? null);
}

/**
 * The pins of the shown net (`old`, drawn by `surface`) in the numbering of `next`, and
 * the limit points to hold them at (null without a surface to take them from).
 */
export function carriedPins(
  surface: LimitSurface | null,
  old: Net | null,
  next: Net,
  pinned: readonly number[],
): { pins: number[]; anchors: Float64Array | null } {
  if (!old) return { pins: [], anchors: null };
  const carried = carryPins(old, next, pinned);
  const kept = pinned.filter((_, index) => carried[index] !== null);
  return {
    pins: carried.filter((control): control is number => control !== null),
    anchors: surface ? pinnedLimits(surface, kept) : null,
  };
}

/** The limit points of the pinned control points (x, y, z each, in their order). */
export function pinnedLimits(surface: LimitSurface, pinned: readonly number[]): Float64Array {
  const limits = new Float64Array(pinned.length * 3);
  pinned.forEach((control, index) => limits.set(surface.limitPoint(control), index * 3));
  return limits;
}

/**
 * Move the pinned control points so that their limit points are back at `anchors`
 * (from `pinnedLimits` before a change), in place; `surface` must show `vertices`.
 */
export function holdPinned(
  surface: LimitSurface,
  vertices: Float64Array,
  pinned: readonly number[],
  anchors: Float64Array,
): void {
  if (pinned.length === 0) return;
  const controls = Uint32Array.from(pinned);
  const current = pinnedLimits(surface, pinned);
  const wanted = anchors.map((anchor, i) => anchor - (current[i] ?? 0));
  const offsets = controlOffsets(surface, controls, wanted);
  controls.forEach((control, index) => {
    for (let axis = 0; axis < 3; axis += 1)
      vertices[control * 3 + axis] =
        (vertices[control * 3 + axis] ?? 0) + (offsets[index * 3 + axis] ?? 0);
  });
  surface.evaluateRows(vertices, surface.rowsOf(controls));
}

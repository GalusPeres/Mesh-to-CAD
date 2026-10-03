// What a click or a Ctrl stroke does in sketch mode, decided from what lies under
// the pointer (pure, so the hover feedback and the action always agree):
// - a click near an entity selects it; inside a closed section outline it fits the
//   outline's shape;
// - Ctrl at a joint of two entities rounds it with the radius of the scan;
// - a Ctrl stroke over a joint rounds it, over two separate entities it forms the
//   corner between them (QuickSurface: Ctrl+paint on a joint / on two ends).

import type { SketchFrame } from '@shared/protocol/generated/sketch';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import { pointDegrees } from './draftGeometry';
import { type Project, pickEntity, pickPoint } from './sketchPicking';
import type { Vec2 } from './sketchMath';

export type Gesture =
  | { kind: 'select'; entity: string }
  | { kind: 'outline'; loop: number; at: Vec2 }
  | { kind: 'fillet'; point: string }
  | { kind: 'corner'; first: string; second: string }
  | { kind: 'none' };

export interface GestureContext {
  sketch: SketchParams;
  /** Closed section outlines in sketch coordinates. */
  loops: readonly (readonly Vec2[])[];
  frame: SketchFrame;
  project: Project;
}

/** Twice the signed area of a closed polygon. */
function doubleArea(polygon: readonly Vec2[]): number {
  let sum = 0;
  polygon.forEach((a, i) => {
    const b = polygon[(i + 1) % polygon.length] as Vec2;
    sum += a[0] * b[1] - b[0] * a[1];
  });
  return sum;
}

export function insidePolygon(point: Vec2, polygon: readonly Vec2[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const a = polygon[i] as Vec2;
    const b = polygon[j] as Vec2;
    if (a[1] > point[1] !== b[1] > point[1]) {
      const x = ((b[0] - a[0]) * (point[1] - a[1])) / (b[1] - a[1]) + a[0];
      if (point[0] < x) inside = !inside;
    }
  }
  return inside;
}

/** The smallest closed outline around a point, as an index into `loops`. */
export function loopAt(loops: readonly (readonly Vec2[])[], point: Vec2): number | null {
  let best: number | null = null;
  let bestArea = Infinity;
  for (const [index, loop] of loops.entries()) {
    if (loop.length < 3 || !insidePolygon(point, loop)) continue;
    const area = Math.abs(doubleArea(loop));
    if (area < bestArea) [best, bestArea] = [index, area];
  }
  return best;
}

/** A point where exactly two lines or arcs meet, near the cursor. */
export function jointAt(context: GestureContext, cursor: Vec2): string | null {
  const degrees = pointDegrees(context.sketch);
  const joints = {
    ...context.sketch,
    points: context.sketch.points.filter((point) => degrees.get(point.id) === 2),
  };
  return pickPoint(joints, context.frame, context.project, cursor);
}

/** What a click at the cursor does (Ctrl held or not). */
export function gestureAt(
  context: GestureContext,
  cursor: Vec2,
  atPlane: Vec2 | null,
  ctrl: boolean,
): Gesture {
  if (ctrl) {
    const point = jointAt(context, cursor);
    return point ? { kind: 'fillet', point } : { kind: 'none' };
  }
  const entity = pickEntity(context.sketch, context.frame, context.project, cursor);
  if (entity) return { kind: 'select', entity };
  const loop = atPlane ? loopAt(context.loops, atPlane) : null;
  return loop !== null && atPlane ? { kind: 'outline', loop, at: atPlane } : { kind: 'none' };
}

/** What a Ctrl stroke along screen positions does. */
export function strokeGesture(context: GestureContext, path: readonly Vec2[]): Gesture {
  const touched: string[] = [];
  for (const cursor of path) {
    const point = jointAt(context, cursor);
    if (point) return { kind: 'fillet', point };
    const entity = pickEntity(context.sketch, context.frame, context.project, cursor);
    if (entity && !touched.includes(entity)) touched.push(entity);
  }
  const curves = touched.filter(
    (id) => context.sketch.entities.find((entity) => entity.id === id)?.type !== 'circle',
  );
  const [first, second] = [curves[0], curves[curves.length - 1]];
  return first && second && first !== second ? { kind: 'corner', first, second } : { kind: 'none' };
}

/** A point well inside a closed outline: the middle of its widest span through the centroid. */
export function interiorPoint(loop: readonly Vec2[]): Vec2 | null {
  if (loop.length < 3) return null;
  const y = loop.reduce((sum, p) => sum + p[1], 0) / loop.length;
  const crossings: number[] = [];
  for (let i = 0, j = loop.length - 1; i < loop.length; j = i, i += 1) {
    const a = loop[i] as Vec2;
    const b = loop[j] as Vec2;
    if (a[1] > y !== b[1] > y) crossings.push(((b[0] - a[0]) * (y - a[1])) / (b[1] - a[1]) + a[0]);
  }
  crossings.sort((p, q) => p - q);
  let best: Vec2 | null = null;
  let width = 0;
  for (let k = 0; k + 1 < crossings.length; k += 2) {
    const [from, to] = [crossings[k] as number, crossings[k + 1] as number];
    if (to - from > width) [best, width] = [[(from + to) / 2, y], to - from];
  }
  return best;
}

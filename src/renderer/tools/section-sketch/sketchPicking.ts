// Screen-space picking of sketch entities, points and section points. The
// viewport projects part coordinates to CSS pixels; everything here is pure.

import type { SketchFrame } from '@shared/protocol/generated/sketch';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import { entityPolyline } from './draftGeometry';
import { type Vec2, type Vec3, distance, segmentDistance, toPart } from './sketchMath';

export type Project = (point: Vec3) => { x: number; y: number } | null;

export const ENTITY_PICK_PX = 8;
export const POINT_PICK_PX = 10;
export const PAINT_RADIUS_PX = 12;

function screen(project: Project, frame: SketchFrame, point: Vec2): Vec2 | null {
  const hit = project(toPart(frame, point));
  return hit ? [hit.x, hit.y] : null;
}

/** The entity drawn closest to the cursor, within `maxPx`. */
export function pickEntity(
  sketch: SketchParams,
  frame: SketchFrame,
  project: Project,
  cursor: Vec2,
  maxPx = ENTITY_PICK_PX,
): string | null {
  let best: { id: string; distance: number } | null = null;
  for (const entity of sketch.entities) {
    const projected = entityPolyline(sketch, entity.id).map((point) =>
      screen(project, frame, point),
    );
    for (let i = 0; i + 1 < projected.length; i += 1) {
      const a = projected[i];
      const b = projected[i + 1];
      if (!a || !b) continue;
      const d = segmentDistance(cursor, a, b);
      if (d <= maxPx && (!best || d < best.distance)) best = { id: entity.id, distance: d };
    }
  }
  return best?.id ?? null;
}

/** The sketch point closest to the cursor, within `maxPx`. */
export function pickPoint(
  sketch: SketchParams,
  frame: SketchFrame,
  project: Project,
  cursor: Vec2,
  maxPx = POINT_PICK_PX,
): string | null {
  let best: { id: string; distance: number } | null = null;
  for (const point of sketch.points) {
    const at = screen(project, frame, [point.x, point.y]);
    if (!at) continue;
    const d = distance(cursor, at);
    if (d <= maxPx && (!best || d < best.distance)) best = { id: point.id, distance: d };
  }
  return best?.id ?? null;
}

/** Snap targets for a typed or clicked position: sketch points and circle and arc centres. */
export function snapTargets(sketch: SketchParams): Vec2[] {
  return [
    ...sketch.points.map((point): Vec2 => [point.x, point.y]),
    ...sketch.entities.flatMap((entity): Vec2[] => (entity.type === 'line' ? [] : [entity.center])),
  ];
}

export function snapToTarget(
  targets: readonly Vec2[],
  frame: SketchFrame,
  project: Project,
  cursor: Vec2,
  fallback: Vec2,
  maxPx = POINT_PICK_PX,
): Vec2 {
  let best: { point: Vec2; distance: number } | null = null;
  for (const target of targets) {
    const at = screen(project, frame, target);
    if (!at) continue;
    const d = distance(cursor, at);
    if (d <= maxPx && (!best || d < best.distance)) best = { point: target, distance: d };
  }
  return best?.point ?? fallback;
}

/**
 * Collects section points under a painting stroke, in the order the stroke first
 * reaches them (the order `sketch.fitEntity` expects).
 */
export class PaintStroke {
  private readonly screenPoints: (Vec2 | null)[];
  private readonly taken = new Set<number>();
  private readonly order: number[] = [];

  constructor(
    private readonly points: readonly Vec2[],
    frame: SketchFrame,
    project: Project,
  ) {
    this.screenPoints = points.map((point) => screen(project, frame, point));
  }

  add(cursor: Vec2, radius = PAINT_RADIUS_PX): void {
    this.screenPoints.forEach((at, index) => {
      if (at && !this.taken.has(index) && distance(cursor, at) <= radius) {
        this.taken.add(index);
        this.order.push(index);
      }
    });
  }

  collected(): Vec2[] {
    return this.order.map((index) => this.points[index] as Vec2);
  }
}

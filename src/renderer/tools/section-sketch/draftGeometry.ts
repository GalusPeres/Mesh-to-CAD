// Geometry of a stored sketch draft: point lookup, carriers, polylines and the
// connectivity of entity ends.

import type {
  SketchEntity,
  SketchParams,
  SketchPoint,
} from '@shared/protocol/generated/sketch-params';

import { type Carrier, type Vec2, arcPolyline } from './sketchMath';

export function pointOf(sketch: SketchParams, id: string): SketchPoint {
  const point = sketch.points.find((candidate) => candidate.id === id);
  if (!point) throw new Error(`sketch point ${id} is missing`);
  return point;
}

export function xy(point: SketchPoint): Vec2 {
  return [point.x, point.y];
}

export function carrierOf(sketch: SketchParams, entity: SketchEntity): Carrier {
  if (entity.type !== 'line')
    return { kind: 'circle', center: entity.center, radius: entity.radius };
  const start = xy(pointOf(sketch, entity.start));
  const end = xy(pointOf(sketch, entity.end));
  return { kind: 'line', point: start, direction: [end[0] - start[0], end[1] - start[1]] };
}

/** How many entity ends meet at each point. */
export function pointDegrees(sketch: SketchParams): Map<string, number> {
  const degrees = new Map(sketch.points.map((point) => [point.id, 0]));
  for (const entity of sketch.entities) {
    if (entity.type === 'circle') continue;
    for (const id of [entity.start, entity.end]) degrees.set(id, (degrees.get(id) ?? 0) + 1);
  }
  return degrees;
}

/** Points where exactly one entity ends (the ends of open chains). */
export function openEnds(sketch: SketchParams): SketchPoint[] {
  const degrees = pointDegrees(sketch);
  return sketch.points.filter((point) => degrees.get(point.id) === 1);
}

/** Sketch-coordinate polyline of an entity (arcs and circles as 3-degree chords). */
export function entityPolyline(sketch: SketchParams, entityId: string): Vec2[] {
  const entity = sketch.entities.find((candidate) => candidate.id === entityId);
  if (!entity) return [];
  if (entity.type === 'circle') {
    const start: Vec2 = [entity.center[0] + entity.radius, entity.center[1]];
    return arcPolyline(entity.center, entity.radius, start, start, true);
  }
  const start = xy(pointOf(sketch, entity.start));
  const end = xy(pointOf(sketch, entity.end));
  if (entity.type === 'line') return [start, end];
  return arcPolyline(entity.center, entity.radius, start, end, entity.ccw);
}

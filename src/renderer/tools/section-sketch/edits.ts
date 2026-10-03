// Edits of a sketch draft. Every function returns a new draft (or a reason why
// the edit is not possible); the kernel then refits the fitted entities with
// `sketch.autoFit` in refit mode, which keeps typed values and moves shared points.

import type {
  DimensionKind,
  SketchDimension,
  SketchEntity,
  SketchParams,
  SketchPoint,
} from '@shared/protocol/generated/sketch-params';

import { carrierOf, openEnds, pointOf, xy } from './draftGeometry';
import { type Vec2, distance, endForAngle, endForLength, intersectCarriers } from './sketchMath';

export type EditResult = { ok: true; sketch: SketchParams } | { ok: false; reason: EditFailure };
export type EditFailure = 'noIntersection' | 'samePoint' | 'noOpenEnds' | 'notConnectable';

type Curve = Extract<SketchEntity, { type: 'line' | 'arc' }>;

/** The next free id with the prefix (`e` entities, `p` points), unique within the sketch. */
export function nextId(sketch: SketchParams, prefix: 'e' | 'p'): string {
  const ids = prefix === 'e' ? sketch.entities.map((e) => e.id) : sketch.points.map((p) => p.id);
  const numbers = ids
    .filter((id) => id.startsWith(prefix))
    .map((id) => Number(id.slice(1)))
    .filter((value) => Number.isInteger(value));
  return `${prefix}${Math.max(0, ...numbers) + 1}`;
}

function withoutUnusedPoints(sketch: SketchParams): SketchParams {
  const used = new Set(
    sketch.entities.flatMap((entity) =>
      entity.type === 'circle' ? [] : [entity.start, entity.end],
    ),
  );
  return { ...sketch, points: sketch.points.filter((point) => used.has(point.id)) };
}

export function deleteEntity(sketch: SketchParams, entityId: string): SketchParams {
  const refersTo = (ids: readonly string[]) => ids.includes(entityId);
  return withoutUnusedPoints({
    ...sketch,
    entities: sketch.entities.filter((entity) => entity.id !== entityId),
    constraints: sketch.constraints.filter((constraint) => !refersTo(constraint.refs)),
    snaps: sketch.snaps.filter((snap) => snap.entity !== entityId && !refersTo(snap.members)),
    dimensions: sketch.dimensions.filter((dimension) => dimension.entity !== entityId),
  });
}

/**
 * Ecke bilden: extend (or trim) two entities to the intersection of their carriers
 * nearest to their closest ends; afterwards both ends are one shared point.
 */
export function formCorner(sketch: SketchParams, firstId: string, secondId: string): EditResult {
  const first = sketch.entities.find((e) => e.id === firstId);
  const second = sketch.entities.find((e) => e.id === secondId);
  if (
    !first ||
    !second ||
    first.type === 'circle' ||
    second.type === 'circle' ||
    first === second
  ) {
    return { ok: false, reason: 'notConnectable' };
  }
  const [endA, endB] = closestEnds(sketch, first, second);
  const hint: Vec2 = [(endA.x + endB.x) / 2, (endA.y + endB.y) / 2];
  const corner = intersectCarriers(carrierOf(sketch, first), carrierOf(sketch, second), hint);
  if (!corner) return { ok: false, reason: 'noIntersection' };
  const merged = { ...endA, x: corner[0], y: corner[1] };
  const renamed = (entity: SketchEntity): SketchEntity => {
    if (entity.type === 'circle') return entity;
    return {
      ...entity,
      start: entity.start === endB.id ? endA.id : entity.start,
      end: entity.end === endB.id ? endA.id : entity.end,
    };
  };
  return {
    ok: true,
    sketch: withoutUnusedPoints({
      ...sketch,
      points: sketch.points.map((point) => (point.id === endA.id ? merged : point)),
      entities: sketch.entities.map(renamed),
    }),
  };
}

function closestEnds(sketch: SketchParams, a: Curve, b: Curve): [SketchPoint, SketchPoint] {
  let best: [SketchPoint, SketchPoint] | null = null;
  for (const idA of [a.start, a.end]) {
    for (const idB of [b.start, b.end]) {
      const pair: [SketchPoint, SketchPoint] = [pointOf(sketch, idA), pointOf(sketch, idB)];
      if (!best || distance(xy(pair[0]), xy(pair[1])) < distance(xy(best[0]), xy(best[1]))) {
        best = pair;
      }
    }
  }
  return best as [SketchPoint, SketchPoint];
}

/** A drawn line between two existing points. */
export function lineBetween(sketch: SketchParams, startId: string, endId: string): EditResult {
  if (startId === endId) return { ok: false, reason: 'samePoint' };
  if (distance(xy(pointOf(sketch, startId)), xy(pointOf(sketch, endId))) < 1e-6) {
    return { ok: false, reason: 'samePoint' };
  }
  const line: SketchEntity = {
    type: 'line',
    id: nextId(sketch, 'e'),
    start: startId,
    end: endId,
    origin: 'drawn',
  };
  return { ok: true, sketch: { ...sketch, entities: [...sketch.entities, line] } };
}

/** A drawn circle from typed centre and radius. */
export function addCircle(sketch: SketchParams, center: Vec2, radius: number): SketchParams {
  const circle: SketchEntity = {
    type: 'circle',
    id: nextId(sketch, 'e'),
    center: [center[0], center[1]],
    radius,
    origin: 'drawn',
  };
  return { ...sketch, entities: [...sketch.entities, circle] };
}

/**
 * Lücke mit Linie schließen: a drawn line between the two closest open ends, or from
 * `fromPointId` to the open end closest to it.
 */
export function closeGap(sketch: SketchParams, fromPointId?: string): EditResult {
  const ends = openEnds(sketch);
  let best: [SketchPoint, SketchPoint] | null = null;
  for (const [i, a] of ends.entries()) {
    if (fromPointId && a.id !== fromPointId) continue;
    for (const b of ends.slice(fromPointId ? 0 : i + 1)) {
      if (b.id === a.id) continue;
      if (!best || distance(xy(a), xy(b)) < distance(xy(best[0]), xy(best[1]))) best = [a, b];
    }
  }
  if (!best) return { ok: false, reason: 'noOpenEnds' };
  return lineBetween(sketch, best[0].id, best[1].id);
}

function withDimension(sketch: SketchParams, dimension: SketchDimension): SketchParams {
  const others = sketch.dimensions.filter(
    (d) => !(d.entity === dimension.entity && d.kind === dimension.kind),
  );
  // A typed radius or centre replaces the snap of the same value.
  const replacedSnaps: Partial<Record<DimensionKind, string>> = {
    radius: 'radius',
    centerX: 'centerX',
    centerY: 'centerY',
    angle: 'angle',
  };
  const snapKind = replacedSnaps[dimension.kind];
  return {
    ...sketch,
    dimensions: [...others, dimension],
    snaps: sketch.snaps.filter(
      (snap) => !(snap.entity === dimension.entity && snap.kind === snapKind),
    ),
  };
}

export function releaseDimension(
  sketch: SketchParams,
  entityId: string,
  kind: DimensionKind,
): SketchParams {
  return {
    ...sketch,
    dimensions: sketch.dimensions.filter((d) => !(d.entity === entityId && d.kind === kind)),
  };
}

function movePoint(sketch: SketchParams, id: string, to: Vec2, fixed: boolean): SketchParams {
  return {
    ...sketch,
    points: sketch.points.map((point) =>
      point.id === id ? { ...point, x: to[0], y: to[1], fixed: fixed || point.fixed } : point,
    ),
  };
}

/** Type the coordinates of a point: it stays there in refits (entities through it follow). */
export function setPoint(sketch: SketchParams, id: string, to: Vec2): SketchParams {
  return movePoint(sketch, id, to, true);
}

export function releasePoint(sketch: SketchParams, id: string): SketchParams {
  return {
    ...sketch,
    points: sketch.points.map((point) => (point.id === id ? { ...point, fixed: false } : point)),
  };
}

/** Type the length or direction of a line; the end point moves, the start stays. */
export function setLineValue(
  sketch: SketchParams,
  lineId: string,
  kind: 'length' | 'angle',
  value: number,
): SketchParams {
  const line = sketch.entities.find((entity) => entity.id === lineId);
  if (!line || line.type !== 'line') return sketch;
  const start = xy(pointOf(sketch, line.start));
  const end = xy(pointOf(sketch, line.end));
  const moved =
    kind === 'length' ? endForLength(start, end, value) : endForAngle(start, end, value);
  const next = movePoint(sketch, line.end, moved, false);
  return line.origin === 'fit' ? withDimension(next, { entity: lineId, kind, value }) : next;
}

/** Type the radius or a centre coordinate of an arc or circle. */
export function setRoundValue(
  sketch: SketchParams,
  entityId: string,
  kind: 'radius' | 'centerX' | 'centerY',
  value: number,
): SketchParams {
  const entity = sketch.entities.find((candidate) => candidate.id === entityId);
  if (!entity || entity.type === 'line') return sketch;
  const center: [number, number] =
    kind === 'centerX'
      ? [value, entity.center[1]]
      : kind === 'centerY'
        ? [entity.center[0], value]
        : [...entity.center];
  const radius = kind === 'radius' ? value : entity.radius;
  const next = {
    ...sketch,
    entities: sketch.entities.map((candidate) =>
      candidate.id === entityId ? { ...entity, center, radius } : candidate,
    ),
  };
  return entity.origin === 'fit' ? withDimension(next, { entity: entityId, kind, value }) : next;
}

/** Remove a snapped value; it stays removed in later refits. */
export function removeSnap(sketch: SketchParams, snapId: string): SketchParams {
  return {
    ...sketch,
    snaps: sketch.snaps.filter((snap) => snap.id !== snapId),
    rejectedSnaps: sketch.rejectedSnaps.includes(snapId)
      ? sketch.rejectedSnaps
      : [...sketch.rejectedSnaps, snapId],
  };
}

export function removeConstraint(sketch: SketchParams, index: number): SketchParams {
  return { ...sketch, constraints: sketch.constraints.filter((_, i) => i !== index) };
}

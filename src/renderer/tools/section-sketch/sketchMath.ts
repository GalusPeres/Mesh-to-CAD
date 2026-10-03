// Plane geometry of the sketch tool: entity values <-> end points, carrier
// intersections for "Ecke bilden", and the mapping between sketch and part
// coordinates. Angles are degrees, lengths millimetres.

import type { SketchFrame } from '@shared/protocol/generated/sketch';

export type Vec2 = readonly [number, number];
export type Vec3 = readonly [number, number, number];

/** An infinite line or a full circle that an entity lies on. */
export type Carrier =
  { kind: 'line'; point: Vec2; direction: Vec2 } | { kind: 'circle'; center: Vec2; radius: number };

const EPSILON = 1e-9;

export function distance(a: Vec2, b: Vec2): number {
  return Math.hypot(b[0] - a[0], b[1] - a[1]);
}

export function lineLength(start: Vec2, end: Vec2): number {
  return distance(start, end);
}

/** Direction of a line from start to end, in [0, 360) degrees from the sketch X axis. */
export function lineAngle(start: Vec2, end: Vec2): number {
  const degrees = (Math.atan2(end[1] - start[1], end[0] - start[0]) * 180) / Math.PI;
  return (degrees + 360) % 360;
}

/** The end point that gives the line this length; start and direction stay. */
export function endForLength(start: Vec2, end: Vec2, length: number): Vec2 {
  const current = lineLength(start, end);
  const direction: Vec2 =
    current > EPSILON ? [(end[0] - start[0]) / current, (end[1] - start[1]) / current] : [1, 0];
  return [start[0] + direction[0] * length, start[1] + direction[1] * length];
}

/** The end point that gives the line this direction; start and length stay. */
export function endForAngle(start: Vec2, end: Vec2, angle: number): Vec2 {
  const length = lineLength(start, end);
  const radians = (angle * Math.PI) / 180;
  return [start[0] + length * Math.cos(radians), start[1] + length * Math.sin(radians)];
}

function lineLine(
  a: Extract<Carrier, { kind: 'line' }>,
  b: Extract<Carrier, { kind: 'line' }>,
): Vec2[] {
  const det = a.direction[0] * b.direction[1] - a.direction[1] * b.direction[0];
  if (Math.abs(det) < 1e-9) return [];
  const dx = b.point[0] - a.point[0];
  const dy = b.point[1] - a.point[1];
  const t = (dx * b.direction[1] - dy * b.direction[0]) / det;
  return [[a.point[0] + t * a.direction[0], a.point[1] + t * a.direction[1]]];
}

function lineCircle(
  line: Extract<Carrier, { kind: 'line' }>,
  circle: Extract<Carrier, { kind: 'circle' }>,
): Vec2[] {
  const [dx, dy] = line.direction;
  const norm = Math.hypot(dx, dy);
  const ux = dx / norm;
  const uy = dy / norm;
  const fx = line.point[0] - circle.center[0];
  const fy = line.point[1] - circle.center[1];
  const along = fx * ux + fy * uy;
  const footX = line.point[0] - along * ux;
  const footY = line.point[1] - along * uy;
  const offset = Math.hypot(footX - circle.center[0], footY - circle.center[1]);
  // A line that misses the circle by a hair (a tangent within scan noise) touches it.
  if (offset > circle.radius + 1e-6 * Math.max(1, circle.radius)) return [];
  const half = Math.sqrt(Math.max(circle.radius ** 2 - offset ** 2, 0));
  return [
    [footX + half * ux, footY + half * uy],
    [footX - half * ux, footY - half * uy],
  ];
}

function circleCircle(
  a: Extract<Carrier, { kind: 'circle' }>,
  b: Extract<Carrier, { kind: 'circle' }>,
): Vec2[] {
  const d = distance(a.center, b.center);
  if (d < EPSILON || d > a.radius + b.radius + 1e-6 || d < Math.abs(a.radius - b.radius) - 1e-6) {
    return [];
  }
  const ux = (b.center[0] - a.center[0]) / d;
  const uy = (b.center[1] - a.center[1]) / d;
  const along = (a.radius ** 2 - b.radius ** 2 + d ** 2) / (2 * d);
  const half = Math.sqrt(Math.max(a.radius ** 2 - along ** 2, 0));
  const baseX = a.center[0] + along * ux;
  const baseY = a.center[1] + along * uy;
  return [
    [baseX - half * uy, baseY + half * ux],
    [baseX + half * uy, baseY - half * ux],
  ];
}

/** The intersection of two carriers closest to `hint`, or null when they do not meet. */
export function intersectCarriers(a: Carrier, b: Carrier, hint: Vec2): Vec2 | null {
  let candidates: Vec2[];
  if (a.kind === 'line' && b.kind === 'line') candidates = lineLine(a, b);
  else if (a.kind === 'line' && b.kind === 'circle') candidates = lineCircle(a, b);
  else if (a.kind === 'circle' && b.kind === 'line') candidates = lineCircle(b, a);
  else if (a.kind === 'circle' && b.kind === 'circle') candidates = circleCircle(a, b);
  else candidates = [];
  let best: Vec2 | null = null;
  for (const candidate of candidates) {
    if (!best || distance(candidate, hint) < distance(best, hint)) best = candidate;
  }
  return best;
}

/** Sketch coordinates (u, v) to part coordinates. */
export function toPart(frame: SketchFrame, point: Vec2): Vec3 {
  const [u, v] = point;
  return [
    frame.origin[0] + u * frame.xDir[0] + v * frame.yDir[0],
    frame.origin[1] + u * frame.xDir[1] + v * frame.yDir[1],
    frame.origin[2] + u * frame.xDir[2] + v * frame.yDir[2],
  ];
}

function dot3(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function sub3(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

/** Where a ray meets the sketch plane, in sketch coordinates; null if it runs parallel. */
export function rayToSketch(frame: SketchFrame, origin: Vec3, direction: Vec3): Vec2 | null {
  const denominator = dot3(direction, frame.normal);
  if (Math.abs(denominator) < 1e-9) return null;
  const t = dot3(sub3(frame.origin, origin), frame.normal) / denominator;
  const hit: Vec3 = [
    origin[0] + t * direction[0] - frame.origin[0],
    origin[1] + t * direction[1] - frame.origin[1],
    origin[2] + t * direction[2] - frame.origin[2],
  ];
  return [dot3(hit, frame.xDir), dot3(hit, frame.yDir)];
}

/** Distance from a point to the segment a-b (screen or sketch coordinates). */
export function segmentDistance(point: Vec2, a: Vec2, b: Vec2): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSq = dx * dx + dy * dy;
  const t =
    lengthSq < EPSILON
      ? 0
      : Math.min(1, Math.max(0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / lengthSq));
  return distance(point, [a[0] + t * dx, a[1] + t * dy]);
}

/** Points along an arc from start to end, counter-clockwise or clockwise (a full turn if closed). */
export function arcPolyline(
  center: Vec2,
  radius: number,
  start: Vec2,
  end: Vec2,
  ccw: boolean,
  stepDeg = 3,
): Vec2[] {
  const a0 = Math.atan2(start[1] - center[1], start[0] - center[0]);
  const a1 = Math.atan2(end[1] - center[1], end[0] - center[0]);
  const turn = 2 * Math.PI;
  let sweep = ccw ? (((a1 - a0) % turn) + turn) % turn : -((((a0 - a1) % turn) + turn) % turn);
  if (Math.abs(sweep) < 1e-9) sweep = ccw ? turn : -turn;
  const count = Math.max(8, Math.ceil(Math.abs(sweep) / ((stepDeg * Math.PI) / 180)));
  return Array.from({ length: count + 1 }, (_, k) => {
    const angle = a0 + (sweep * k) / count;
    return [center[0] + radius * Math.cos(angle), center[1] + radius * Math.sin(angle)] as Vec2;
  });
}

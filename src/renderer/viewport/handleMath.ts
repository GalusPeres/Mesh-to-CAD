// Drag maths of the handles: every handle turns the pointer ray into a value.

import * as THREE from 'three';

import type { Ray, Vec3 } from './api';

const vector = (value: Vec3) => new THREE.Vector3(value[0], value[1], value[2]);
const tuple = (value: THREE.Vector3): Vec3 => [value.x, value.y, value.z];

/** Parameter along `origin + t * direction` (direction normalised) closest to a ray. */
export function closestAlongAxis(origin: Vec3, direction: Vec3, ray: Ray): number {
  const d = vector(direction).normalize();
  const r = vector(ray.direction).normalize();
  const w = vector(origin).sub(vector(ray.origin));
  const b = d.dot(r);
  const denominator = 1 - b * b;
  // The ray runs along the axis: no defined closest point.
  if (Math.abs(denominator) < 1e-9) return Number.NaN;
  return (b * r.dot(w) - d.dot(w)) / denominator;
}

/** Intersection of a ray with a plane, or null when they are parallel. */
export function intersectPlane(ray: Ray, point: Vec3, normal: Vec3): Vec3 | null {
  const n = vector(normal).normalize();
  const direction = vector(ray.direction);
  const denominator = n.dot(direction);
  if (Math.abs(denominator) < 1e-9) return null;
  const t = n.dot(vector(point).sub(vector(ray.origin))) / denominator;
  return tuple(vector(ray.origin).addScaledVector(direction, t));
}

/** Angle in degrees of a point around an axis, measured from `reference` (right-handed). */
export function angleAround(point: Vec3, center: Vec3, axis: Vec3, reference: Vec3): number {
  const a = vector(axis).normalize();
  const x = vector(reference).normalize();
  const y = a.clone().cross(x);
  const v = vector(point).sub(vector(center));
  return (Math.atan2(v.dot(y), v.dot(x)) * 180) / Math.PI;
}

/** An angle difference in degrees mapped to (-180, 180]. */
export function wrapDegrees(angle: number): number {
  const wrapped = ((((angle + 180) % 360) + 360) % 360) - 180;
  return wrapped === -180 ? 180 : wrapped;
}

/** `direction` rotated by `degrees` around `axis` (right-handed). */
export function rotateAround(direction: Vec3, axis: Vec3, degrees: number): Vec3 {
  const rotated = vector(direction).applyAxisAngle(
    vector(axis).normalize(),
    (degrees * Math.PI) / 180,
  );
  return tuple(rotated);
}

/** Some unit vector perpendicular to `normal`, preferring the world axes. */
export function perpendicular(normal: Vec3): Vec3 {
  const n = vector(normal).normalize();
  const helper = Math.abs(n.z) < 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
  return tuple(helper.cross(n).normalize());
}

/** Distance in pixels from a point to a screen segment. */
export function distanceToSegment(
  point: { x: number; y: number },
  a: { x: number; y: number },
  b: { x: number; y: number },
): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const length = dx * dx + dy * dy;
  const t =
    length > 0
      ? Math.min(1, Math.max(0, ((point.x - a.x) * dx + (point.y - a.y) * dy) / length))
      : 0;
  return Math.hypot(point.x - (a.x + t * dx), point.y - (a.y + t * dy));
}

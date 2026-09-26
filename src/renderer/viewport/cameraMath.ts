// Camera placement for standard views and fitting, Z up (CAD convention).

import type { StandardView, Vec3 } from './api';

export interface ViewDirection {
  /** Direction the camera looks in (from the camera towards the target). */
  direction: Vec3;
  up: Vec3;
}

const DIAGONAL = 1 / Math.sqrt(3);

export const STANDARD_VIEWS: Record<StandardView, ViewDirection> = {
  front: { direction: [0, 1, 0], up: [0, 0, 1] },
  back: { direction: [0, -1, 0], up: [0, 0, 1] },
  left: { direction: [1, 0, 0], up: [0, 0, 1] },
  right: { direction: [-1, 0, 0], up: [0, 0, 1] },
  top: { direction: [0, 0, -1], up: [0, 1, 0] },
  bottom: { direction: [0, 0, 1], up: [0, -1, 0] },
  iso: { direction: [-DIAGONAL, DIAGONAL, -DIAGONAL], up: [0, 0, 1] },
};

export interface Sphere {
  center: Vec3;
  radius: number;
}

/** The smallest sphere around an axis-aligned box. */
export function boxSphere(min: Vec3, max: Vec3): Sphere {
  const center: Vec3 = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
  const radius = Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]) / 2;
  return { center, radius: Math.max(radius, 1e-3) };
}

/** Distance at which a perspective camera sees the whole sphere. */
export function perspectiveDistance(
  radius: number,
  verticalFovDeg: number,
  aspect: number,
): number {
  const vertical = (verticalFovDeg * Math.PI) / 360;
  const horizontal = Math.atan(Math.tan(vertical) * aspect);
  return radius / Math.sin(Math.min(vertical, horizontal));
}

/** Half height of an orthographic frustum that shows the whole sphere with a margin. */
export function orthographicHalfHeight(radius: number, aspect: number, margin = 1.1): number {
  return (radius * margin) / Math.min(1, aspect);
}

/** Camera position for looking in `direction` at `target` from `distance`. */
export function cameraPosition(target: Vec3, direction: Vec3, distance: number): Vec3 {
  return [
    target[0] - direction[0] * distance,
    target[1] - direction[1] * distance,
    target[2] - direction[2] * distance,
  ];
}

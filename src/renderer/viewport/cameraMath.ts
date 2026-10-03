// Camera placement for standard views, fitting and orbiting, Z up (CAD convention).

import * as THREE from 'three';

import type { StandardView, Vec3 } from './api';

const Z_UP = new THREE.Vector3(0, 0, 1);

export interface CameraPose {
  position: THREE.Vector3;
  quaternion: THREE.Quaternion;
  target: THREE.Vector3;
  halfHeight: number;
}

/**
 * Rotate a camera pose around a pivot: yaw around world Z, then pitch around the
 * camera's right axis. The pivot keeps its place on the screen.
 */
export function orbitPose(
  pose: CameraPose,
  pivot: THREE.Vector3,
  yaw: number,
  pitch: number,
): void {
  const right = new THREE.Vector3(1, 0, 0).applyQuaternion(pose.quaternion);
  const rotation = new THREE.Quaternion()
    .setFromAxisAngle(Z_UP, yaw)
    .multiply(new THREE.Quaternion().setFromAxisAngle(right, pitch));
  pose.position.sub(pivot).applyQuaternion(rotation).add(pivot);
  pose.target.sub(pivot).applyQuaternion(rotation).add(pivot);
  pose.quaternion.premultiply(rotation).normalize();
}

/** Orientation of a camera looking in `direction` with `up` pointing up on screen. */
export function viewQuaternion(direction: Vec3, up: Vec3): THREE.Quaternion {
  const matrix = new THREE.Matrix4().lookAt(
    new THREE.Vector3(0, 0, 0),
    new THREE.Vector3(...direction),
    new THREE.Vector3(...up),
  );
  return new THREE.Quaternion().setFromRotationMatrix(matrix);
}

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

/** Ease-out used by camera transitions (docs/DESIGN.md 2.5). */
export function easeOut(t: number): number {
  const clamped = Math.min(1, Math.max(0, t));
  return 1 - (1 - clamped) ** 3;
}

/** Camera transitions take 250 ms, instant with reduced motion. */
export const TRANSITION_MS = 250;

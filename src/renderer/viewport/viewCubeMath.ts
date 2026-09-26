// View cube zones: 6 faces, 12 edges and 8 corners (26 views). A zone is a
// vector with components in {-1, 0, 1}; the camera looks from the zone towards
// the cube centre.

import type { Vec3 } from './api';
import { STANDARD_VIEWS, type ViewDirection } from './cameraMath';

/** Width of the edge and corner bands as a fraction of the cube size. */
export const ZONE_BAND = 0.2;

/** The zone of a point on the surface of the unit cube centred at the origin. */
export function cubeZone(point: Vec3, band = ZONE_BAND): Vec3 {
  const extent = Math.max(Math.abs(point[0]), Math.abs(point[1]), Math.abs(point[2]));
  const limit = extent - band;
  const classify = (value: number) => (Math.abs(value) > limit ? Math.sign(value) : 0);
  return [classify(point[0]), classify(point[1]), classify(point[2])];
}

/** View direction and up vector for a zone. */
export function zoneView(zone: Vec3): ViewDirection {
  const length = Math.hypot(zone[0], zone[1], zone[2]) || 1;
  const direction: Vec3 = [-zone[0] / length, -zone[1] / length, -zone[2] / length];
  if (zone[0] === 0 && zone[1] === 0)
    return zone[2] > 0 ? STANDARD_VIEWS.top : STANDARD_VIEWS.bottom;
  return { direction, up: [0, 0, 1] };
}

/** All 26 zones. */
export const CUBE_ZONES: readonly Vec3[] = [-1, 0, 1].flatMap((x) =>
  [-1, 0, 1].flatMap((y) =>
    [-1, 0, 1].flatMap((z): Vec3[] => (x === 0 && y === 0 && z === 0 ? [] : [[x, y, z]])),
  ),
);

/** Cube faces: outward normal, the up direction of its label, and its label key. */
export const CUBE_FACES: readonly { normal: Vec3; up: Vec3; label: string }[] = [
  { normal: [0, -1, 0], up: [0, 0, 1], label: 'front' },
  { normal: [0, 1, 0], up: [0, 0, 1], label: 'back' },
  { normal: [-1, 0, 0], up: [0, 0, 1], label: 'left' },
  { normal: [1, 0, 0], up: [0, 0, 1], label: 'right' },
  { normal: [0, 0, 1], up: [0, 1, 0], label: 'top' },
  { normal: [0, 0, -1], up: [0, -1, 0], label: 'bottom' },
];

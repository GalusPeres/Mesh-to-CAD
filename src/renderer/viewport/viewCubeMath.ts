// View cube zones: 6 faces, 12 edges and 8 corners (26 views). A zone is a
// vector with components in {-1, 0, 1}; the camera looks from the zone towards
// the cube centre. The cube spans [-1, 1] on every axis.

import type { Vec3 } from './api';
import { STANDARD_VIEWS, type ViewDirection } from './cameraMath';

/** Width of the edge and corner bands as a fraction of the cube's half size. */
export const ZONE_BAND = 0.2;

/** The zone of a point on the surface of the cube. */
export function cubeZone(point: Vec3, band = ZONE_BAND): Vec3 {
  const extent = Math.max(Math.abs(point[0]), Math.abs(point[1]), Math.abs(point[2]));
  const limit = extent - band;
  const classify = (value: number) => (Math.abs(value) > limit ? Math.sign(value) : 0);
  return [classify(point[0]), classify(point[1]), classify(point[2])];
}

/** View direction and up vector for a zone. */
export function zoneView(zone: Vec3): ViewDirection {
  if (zone[0] === 0 && zone[1] === 0)
    return zone[2] > 0 ? STANDARD_VIEWS.top : STANDARD_VIEWS.bottom;
  const length = Math.hypot(zone[0], zone[1], zone[2]);
  return { direction: [-zone[0] / length, -zone[1] / length, -zone[2] / length], up: [0, 0, 1] };
}

/** All 26 zones. */
export const CUBE_ZONES: readonly Vec3[] = [-1, 0, 1].flatMap((x) =>
  [-1, 0, 1].flatMap((y) =>
    [-1, 0, 1].flatMap((z): Vec3[] => (x === 0 && y === 0 && z === 0 ? [] : [[x, y, z]])),
  ),
);

/** Cube faces: outward normal, the up direction of its label, and its label key. */
export const CUBE_FACES = [
  { normal: [0, -1, 0], up: [0, 0, 1], label: 'front' },
  { normal: [0, 1, 0], up: [0, 0, 1], label: 'back' },
  { normal: [-1, 0, 0], up: [0, 0, 1], label: 'left' },
  { normal: [1, 0, 0], up: [0, 0, 1], label: 'right' },
  { normal: [0, 0, 1], up: [0, 1, 0], label: 'top' },
  { normal: [0, 0, -1], up: [0, -1, 0], label: 'bottom' },
] as const satisfies readonly { normal: Vec3; up: Vec3; label: string }[];

export interface CubePiece {
  face: (typeof CUBE_FACES)[number];
  /** Centre and extent of the piece in the face's (right, up) directions. */
  center: Vec3;
  width: number;
  height: number;
  zone: Vec3;
}

const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];

/** Right direction of a face seen from outside with its label upright. */
export function faceRight(face: (typeof CUBE_FACES)[number]): Vec3 {
  return cross(face.up, face.normal);
}

/** The 54 pieces: every face split into a 3 x 3 grid along the zone bands. */
export function cubePieces(): CubePiece[] {
  const inner = 1 - ZONE_BAND;
  const spans: [number, number][] = [
    [-1, -inner],
    [-inner, inner],
    [inner, 1],
  ];
  return CUBE_FACES.flatMap((face) => {
    const right = faceRight(face);
    return spans.flatMap(([u0, u1]) =>
      spans.map(([v0, v1]): CubePiece => {
        const cu = (u0 + u1) / 2;
        const cv = (v0 + v1) / 2;
        const [n, up] = [face.normal, face.up];
        const center: Vec3 = [
          n[0] + right[0] * cu + up[0] * cv,
          n[1] + right[1] * cu + up[1] * cv,
          n[2] + right[2] * cu + up[2] * cv,
        ];
        return { face, center, width: u1 - u0, height: v1 - v0, zone: cubeZone(center) };
      }),
    );
  });
}

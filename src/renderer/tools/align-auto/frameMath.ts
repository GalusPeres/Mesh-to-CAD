// Rigid scan-to-part transforms as 16 row-major numbers (ARCHITECTURE.md 4.2).
// The viewport shows the scan with the committed transform; a previewed alignment is
// drawn as its coordinate frame expressed in those displayed coordinates.

export type Vec3 = [number, number, number];

/** A rigid transform `p' = R p + t` as rotation rows and translation. */
interface Rigid {
  rows: [Vec3, Vec3, Vec3];
  translation: Vec3;
}

function rigid(matrix: readonly number[]): Rigid {
  const m = (index: number) => matrix[index] ?? 0;
  return {
    rows: [
      [m(0), m(1), m(2)],
      [m(4), m(5), m(6)],
      [m(8), m(9), m(10)],
    ],
    translation: [m(3), m(7), m(11)],
  };
}

function apply(transform: Rigid, point: Vec3): Vec3 {
  const [r0, r1, r2] = transform.rows;
  const [x, y, z] = point;
  return [
    r0[0] * x + r0[1] * y + r0[2] * z + transform.translation[0],
    r1[0] * x + r1[1] * y + r1[2] * z + transform.translation[1],
    r2[0] * x + r2[1] * y + r2[2] * z + transform.translation[2],
  ];
}

/** `R^T (p - t)`: from part coordinates back to scan coordinates. */
function applyInverse(transform: Rigid, point: Vec3): Vec3 {
  const [r0, r1, r2] = transform.rows;
  const d: Vec3 = [
    point[0] - transform.translation[0],
    point[1] - transform.translation[1],
    point[2] - transform.translation[2],
  ];
  return [
    r0[0] * d[0] + r1[0] * d[1] + r2[0] * d[2],
    r0[1] * d[0] + r1[1] * d[1] + r2[1] * d[2],
    r0[2] * d[0] + r1[2] * d[1] + r2[2] * d[2],
  ];
}

/**
 * Maps points given in the coordinates of the previewed alignment (`next`) into the
 * coordinates the scan is displayed in (`current`), and back.
 */
export interface FrameMapping {
  toDisplay(point: Vec3): Vec3;
  fromDisplay(point: Vec3): Vec3;
}

export function frameMapping(current: readonly number[], next: readonly number[]): FrameMapping {
  const shown = rigid(current);
  const previewed = rigid(next);
  return {
    toDisplay: (point) => apply(shown, applyInverse(previewed, point)),
    fromDisplay: (point) => apply(previewed, applyInverse(shown, point)),
  };
}

export interface Footprint {
  min: Vec3;
  max: Vec3;
}

/**
 * Bounding box, in the previewed part coordinates, of displayed points (face
 * centroids, 3 floats each). At most `limit` evenly spread points are used.
 */
export function footprint(
  mapping: FrameMapping,
  displayed: Float32Array,
  limit = 50_000,
): Footprint | null {
  const count = Math.floor(displayed.length / 3);
  if (count === 0) return null;
  const step = Math.max(1, Math.ceil(count / limit));
  const min: Vec3 = [Infinity, Infinity, Infinity];
  const max: Vec3 = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < count; index += step) {
    const point = mapping.fromDisplay([
      displayed[3 * index] ?? 0,
      displayed[3 * index + 1] ?? 0,
      displayed[3 * index + 2] ?? 0,
    ]);
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis] ?? Infinity, point[axis] ?? 0);
      max[axis] = Math.max(max[axis] ?? -Infinity, point[axis] ?? 0);
    }
  }
  return { min, max };
}

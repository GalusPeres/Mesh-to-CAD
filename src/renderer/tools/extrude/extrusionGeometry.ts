// Geometry the extrude panel reads from its own preview: where the profile lies, which
// way the extrusion goes, and how far the scan reaches above the profile. The start
// and end caps are found through the face tags of the previewed body (`<id>:cap:start`,
// `<id>:cap:end`), so no sketch geometry has to be known in the renderer.

export type Vec3 = [number, number, number];

export interface MeshData {
  positions: Float32Array;
  indices: Uint32Array;
  faceIds: Uint32Array;
}

export interface Caps {
  /** Area-weighted centroids of the start and end cap. */
  start: Vec3;
  end: Vec3;
  /** Unit direction from the start cap to the end cap. */
  direction: Vec3;
  /** Triangles of the start cap, 9 numbers each (the profile's footprint). */
  footprint: Float32Array;
}

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const length = (a: Vec3): number => Math.sqrt(dot(a, a));
const scale = (a: Vec3, factor: number): Vec3 => [a[0] * factor, a[1] * factor, a[2] * factor];
export const addScaled = (a: Vec3, b: Vec3, factor: number): Vec3 => [
  a[0] + b[0] * factor,
  a[1] + b[1] * factor,
  a[2] + b[2] * factor,
];

function vertex(mesh: MeshData, index: number): Vec3 {
  return [
    mesh.positions[index * 3]!,
    mesh.positions[index * 3 + 1]!,
    mesh.positions[index * 3 + 2]!,
  ];
}

/** Triangles of one B-Rep face and their area-weighted centroid. */
function faceTriangles(
  mesh: MeshData,
  face: number,
): { triangles: number[]; centroid: Vec3 } | null {
  const triangles: number[] = [];
  let area = 0;
  let centroid: Vec3 = [0, 0, 0];
  for (let t = 0; t < mesh.faceIds.length; t++) {
    if (mesh.faceIds[t] !== face) continue;
    const a = vertex(mesh, mesh.indices[t * 3]!);
    const b = vertex(mesh, mesh.indices[t * 3 + 1]!);
    const c = vertex(mesh, mesh.indices[t * 3 + 2]!);
    const weight = length(cross(sub(b, a), sub(c, a))) / 2;
    centroid = addScaled(
      centroid,
      [a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2]],
      weight / 3,
    );
    area += weight;
    triangles.push(...a, ...b, ...c);
  }
  return area > 0 ? { triangles, centroid: scale(centroid, 1 / area) } : null;
}

/** Start and end cap of extrusion `featureId` in a previewed body, if both exist. */
export function findCaps(
  mesh: MeshData,
  faceTags: readonly string[],
  featureId: string,
): Caps | null {
  const start = faceTags.indexOf(`${featureId}:cap:start`);
  const end = faceTags.indexOf(`${featureId}:cap:end`);
  if (start < 0 || end < 0) return null;
  const startFace = faceTriangles(mesh, start);
  const endFace = faceTriangles(mesh, end);
  if (!startFace || !endFace) return null;
  const axis = sub(endFace.centroid, startFace.centroid);
  const distance = length(axis);
  if (distance < 1e-9) return null;
  return {
    start: startFace.centroid,
    end: endFace.centroid,
    direction: scale(axis, 1 / distance),
    footprint: new Float32Array(startFace.triangles),
  };
}

/** Two unit vectors perpendicular to `normal`. */
function planeBasis(normal: Vec3): [Vec3, Vec3] {
  const helper: Vec3 = Math.abs(normal[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
  const u = cross(normal, helper);
  const unitU = scale(u, 1 / length(u));
  return [unitU, cross(normal, unitU)];
}

const GRID = 256;

/**
 * How far the scan reaches from the profile plane along `direction`, measured over the
 * profile's footprint: a high quantile of the heights of the scan points above the
 * footprint, so single spikes do not count. Returns null when no scan point lies above it.
 *
 * `points` are scan face centroids (x, y, z per point) in part coordinates.
 */
export function scanExtent(
  points: Float32Array,
  footprint: Float32Array,
  origin: Vec3,
  direction: Vec3,
  quantile = 0.998,
): number | null {
  const [u, v] = planeBasis(direction);
  const triangleCount = footprint.length / 9;
  if (triangleCount === 0) return null;
  const project = (x: number, y: number, z: number): [number, number] => {
    const relative: Vec3 = [x - origin[0], y - origin[1], z - origin[2]];
    return [dot(relative, u), dot(relative, v)];
  };
  const corners: [number, number][] = [];
  for (let i = 0; i < footprint.length; i += 3) {
    corners.push(project(footprint[i]!, footprint[i + 1]!, footprint[i + 2]!));
  }
  let minU = Infinity;
  let minV = Infinity;
  let maxU = -Infinity;
  let maxV = -Infinity;
  for (const [a, b] of corners) {
    minU = Math.min(minU, a);
    maxU = Math.max(maxU, a);
    minV = Math.min(minV, b);
    maxV = Math.max(maxV, b);
  }
  const cellU = (maxU - minU) / GRID || 1;
  const cellV = (maxV - minV) / GRID || 1;
  // Rasterise the footprint once: a cell counts when its centre lies in a triangle.
  const covered = new Uint8Array(GRID * GRID);
  for (let t = 0; t < triangleCount; t++) {
    const [a, b, c] = [corners[t * 3]!, corners[t * 3 + 1]!, corners[t * 3 + 2]!];
    const i0 = Math.max(0, Math.floor((Math.min(a[0], b[0], c[0]) - minU) / cellU));
    const i1 = Math.min(GRID - 1, Math.floor((Math.max(a[0], b[0], c[0]) - minU) / cellU));
    const j0 = Math.max(0, Math.floor((Math.min(a[1], b[1], c[1]) - minV) / cellV));
    const j1 = Math.min(GRID - 1, Math.floor((Math.max(a[1], b[1], c[1]) - minV) / cellV));
    for (let i = i0; i <= i1; i++) {
      for (let j = j0; j <= j1; j++) {
        const p: [number, number] = [minU + (i + 0.5) * cellU, minV + (j + 0.5) * cellV];
        if (inTriangle(p, a, b, c)) covered[i * GRID + j] = 1;
      }
    }
  }
  const heights: number[] = [];
  for (let k = 0; k < points.length; k += 3) {
    const x = points[k]!;
    const y = points[k + 1]!;
    const z = points[k + 2]!;
    const [pu, pv] = project(x, y, z);
    const i = Math.floor((pu - minU) / cellU);
    const j = Math.floor((pv - minV) / cellV);
    if (i < 0 || j < 0 || i >= GRID || j >= GRID || !covered[i * GRID + j]) continue;
    const height =
      (x - origin[0]) * direction[0] +
      (y - origin[1]) * direction[1] +
      (z - origin[2]) * direction[2];
    if (height > 0) heights.push(height);
  }
  if (heights.length === 0) return null;
  heights.sort((a, b) => a - b);
  const high = heights[Math.min(heights.length - 1, Math.floor(quantile * (heights.length - 1)))]!;
  // The quantile lies in the noise band of the farthest surface; its median is the surface.
  const band = heights.filter((height) => height >= high - TOP_BAND_MM && height <= high);
  return band[Math.floor((band.length - 1) / 2)]!;
}

const TOP_BAND_MM = 0.5;

function inTriangle(
  p: [number, number],
  a: [number, number],
  b: [number, number],
  c: [number, number],
): boolean {
  const side = (p1: [number, number], p2: [number, number], p3: [number, number]) =>
    (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1]);
  const d1 = side(p, a, b);
  const d2 = side(p, b, c);
  const d3 = side(p, c, a);
  const negative = d1 < 0 || d2 < 0 || d3 < 0;
  const positive = d1 > 0 || d2 > 0 || d3 > 0;
  return !(negative && positive);
}
